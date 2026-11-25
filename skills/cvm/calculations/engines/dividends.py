"""engines/dividends.py -- DPA (Dividends Per Share) TTM engine.

Gets trailing twelve months dividends per share at any historical date.
[v1.26.1] TWO merged sources (same union the Proventos tab / Carteira
join ride — webui/services/proventos.py):

  1. B3 dividends API (dividends.db cash_dividends) — the deep history,
     now SHARE-CLASS CORRECT: the API returns one row per class under
     the same ticker (PETR3 ON + PETR4 PN under "PETR4"), so the old
     ``SUM(rate) WHERE ticker=?`` DOUBLE-counted every dual-class event.
     Rows are now grouped by (label, dates, related_to) and the group
     keeps ONE row — the one matching the ticker's ISIN (resolved from
     cotahist) or, without an ISIN, the class heuristic from the ticker
     digit (even → preferencial "PR", odd → ordinária "OR"; same
     convention as ProventosService._pick_class_row).
  2. DDM agenda (ddm dividends.db) — the recent-window agenda the B3
     API often misses; merged with NO duplicates (same type + ex-dates
     within 5 days + rates within 2% ⇒ duplicate, B3 wins — the
     sources follow slightly different date conventions and rounding).

DPA TTM ALGORITHM
-----------------
For a date D, sum all cash dividends with an event date in [D - 365, D]:
  DPA_TTM = SUM(rate WHERE event_date BETWEEN D-365 AND D)

The `rate` field is already per-share (R$/share), so we just sum the
rates in the 12-month window. No shares outstanding needed.

DATE RESOLUTION
---------------
The B3 API returns three dates, but `paymentDate` is often NULL for
older dividends. We use COALESCE to pick the best available date:

  event_date = COALESCE(payment_date, last_date_prior, approved_on)

  - payment_date:   when the dividend was actually paid (often NULL for old data)
  - last_date_prior: ex-dividend date (most relevant for yield — must own stock
                     before this date to receive the dividend)
  - approved_on:    when the board declared the dividend (always populated)

This fallback dramatically increases data coverage. Without it, only
recent dividends (with payment_date set) are counted — older ones are
missed. DDM rows use ex_date → record_date → payment_date.

JCP (Juros sobre Capital Próprio) is included — it's a real cash
distribution to shareholders, so it counts as a dividend for yield
purposes. Rendimento/Restituição rows (when B3 carries them) count too.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.dividends import dividends_at, dividends_periods
    d = dividends_at("PETR4", "2024-06-30")  # -> 1.85 (R$/share TTM)
    ps = dividends_periods("PETR4")          # -> [{date, dpa}, ...]
"""
# Color scheme: skills/_colors/dpa.py — 11 ranges (salmon → blue gradient for DPA values)

from __future__ import annotations

import time as _time
from datetime import datetime, timedelta
from typing import Any

from skills._base import engine_cached  # [v1.8 F7]


# SQL expression for the best available date (v1.3.1 fix).
# payment_date is often NULL for older dividends — fall back to
# last_date_prior (ex-dividend date), then approved_on (declaration date).
_EVENT_DATE_EXPR = "COALESCE(payment_date, last_date_prior, approved_on)"

# [v1.26.1] Module-level merged-events memo — dividends_periods iterates
# every event date × dividends_at, so the merged build (3 SQL reads)
# must not run per point. 60s TTL, same convention as the webui services.
_EVENTS_TTL = 60.0
_events_memo: dict[str, tuple[float, list[dict]]] = {}

# B3 label → type_key (the merge's type axis — mirrors the Proventos
# tab's _TYPES map so "Dividendo" and "DIVIDENDO" are the same thing).
_B3_TYPE_KEYS = {
    "DIVIDENDO": "div",
    "JRS CAP PROPRIO": "jcp",
    "RENDIMENTO": "rend",
    "RESTITUICAO": "rest",
    "RESTITUIÇÃO": "rest",
}
_DDM_TYPE_KEYS = {"Dividendo": "div", "JCP": "jcp"}


def _ticker_isin(ticker: str) -> str | None:
    """The ticker's ISIN from cotahist (None when unavailable).

    Same resolution compute_adjusted_close uses — DISTINCT isin for the
    symbol. Used to pick the right share-class row inside each B3
    event group (PETR4 ≠ PETR3 rates).
    """
    try:
        import sqlite3
        from data_sources.b3.cotahist.catalog import connect as _connect
    except ImportError:
        return None
    try:
        conn = _connect(read_only=True)
        try:
            row = conn.execute(
                "SELECT DISTINCT isin FROM cotahist "
                "WHERE symbol = ? AND isin IS NOT NULL AND isin != '' LIMIT 1",
                (ticker.strip().upper(),),
            ).fetchone()
        finally:
            conn.close()
        if row:
            return row["isin"] if isinstance(row, sqlite3.Row) else row[0]
    except Exception:
        pass
    return None


def _pick_class_row(rows: list[dict], ticker: str) -> dict:
    """When share classes carry DIFFERENT rates, pick the ticker's class.

    ISIN convention: the share-class marker sits at NSIN positions 7-8
    (string slice [9:11]): 'PR' = preferencial, 'OR' = ordinária. Ticker
    suffix even digit → PN (prefer 'PR'); odd → ON (prefer 'OR'); units
    and anything unmatched → highest rate (same heuristic as the
    Proventos tab).
    """
    digit = ticker[-1] if ticker and ticker[-1].isdigit() else ""
    want = "PR" if digit in "024568" else ("OR" if digit else None)
    if want:
        for r in rows:
            if (r.get("isin_code") or "")[9:11] == want:
                return r
    return max(rows, key=lambda r: (r.get("rate") or 0.0))


def _b3_events(ticker: str) -> list[dict]:
    """Class-corrected B3 cash_dividends events for `ticker`.

    One row per economic event: rows group by (label, approved_on,
    last_date_prior, payment_date, related_to) and the group keeps ONE
    representative — the ISIN match when cotahist knows the ticker's
    class, else the class heuristic, else any (rates equal anyway).
    """
    try:
        from data_sources.b3.dividends.catalog import connect
    except (ImportError, FileNotFoundError):
        return []
    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return []
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT label, isin_code, approved_on, last_date_prior, "
            "       rate, related_to, payment_date "
            "FROM cash_dividends WHERE ticker = ?",
            (ticker,),
        ).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()
    if not rows:
        return []

    isin = _ticker_isin(ticker)

    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for r in rows:
        key = (r.get("label"), r.get("approved_on"), r.get("last_date_prior"),
               r.get("payment_date"), r.get("related_to"))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    out: list[dict] = []
    for key in order:
        grp = groups[key]
        keep = None
        if isin:
            for r in grp:
                if r.get("isin_code") == isin:
                    keep = r
                    break
        if keep is None:
            rates = {r.get("rate") for r in grp
                     if r.get("rate") is not None}
            keep = grp[0] if len(rates) <= 1 else _pick_class_row(grp, ticker)
        out.append(keep)
    return out


def _ddm_events(ticker: str) -> list[dict]:
    """DDM agenda events for `ticker` (recent window; graceful empty)."""
    try:
        from data_sources.ddm.dividends.catalog import connect as ddm_connect
    except ImportError:
        return []
    try:
        conn = ddm_connect(read_only=True)
    except FileNotFoundError:
        return []
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT tipo, value, record_date, ex_date, payment_date "
            "FROM dividends WHERE ticker = ?", (ticker,)).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()
    return rows


def _iso(v: Any) -> str:
    s = str(v or "")
    return s[:10] if len(s) >= 10 else ""


def _norm_event(src: str, type_key: str, rate: float | None,
                ev_date: str, pay_date: str, raw: dict,
                match_dates: tuple = ()) -> dict:
    return {"src": src, "type_key": type_key, "rate": rate,
            "date": ev_date, "pay": pay_date, "raw": raw,
            "match_dates": match_dates or (ev_date,)}


def _merged_events(ticker: str) -> list[dict]:
    """B3 ∪ DDM events (memoized 60s) — the DPA ground truth.

    DDM duplicates drop (same type_key + dates within 5 days + rates
    within 2% — the sources follow slightly different date conventions
    and rounding); B3 rows win on collision (they carry approved_on +
    remarks + the share-class detail).
    """
    tk = ticker.strip().upper()
    hit = _events_memo.get(tk)
    now = _time.monotonic()
    if hit and now - hit[0] < _EVENTS_TTL:
        return hit[1]

    events: list[dict] = []
    for r in _b3_events(tk):
        rate = r.get("rate")
        try:
            rate = float(rate) if rate is not None else None
        except (TypeError, ValueError):
            rate = None
        type_key = _B3_TYPE_KEYS.get(
            (r.get("label") or "").strip().upper(), "outros")
        # [dedupe axis] The B3 event_date prefers payment_date, but the
        # DDM agenda anchors on the EX-date — a duplicate can sit ~a
        # month away on the payment axis while being 1 day off on the
        # ex axis. match_dates carries ALL THREE B3 dates so the
        # near-date check probes each (the Proventos tab's merge
        # compares ex×ex for the same reason).
        mdates = tuple(d for d in (r.get("last_date_prior"),
                                   r.get("payment_date"),
                                   r.get("approved_on")) if d)
        events.append(_norm_event(
            "b3", type_key, rate,
            r.get("payment_date") or r.get("last_date_prior")
            or r.get("approved_on") or "",
            r.get("payment_date") or "", r, match_dates=mdates))

    for r in _ddm_events(tk):
        tipo = (r.get("tipo") or "").strip()
        type_key = _DDM_TYPE_KEYS.get(tipo, "outros")
        if type_key == "outros":
            continue  # agenda publishes only Dividendo/JCP anyway
        try:
            rate = float(r.get("value")) if r.get("value") is not None else None
        except (TypeError, ValueError):
            continue
        ex = _iso(r.get("ex_date")) or _iso(r.get("record_date"))
        pay = _iso(r.get("payment_date"))
        ev_date = ex or pay
        if not ev_date or rate is None:
            continue
        dup = False
        for ev in events:
            if ev["type_key"] != type_key:
                continue
            near = False
            for md in ev.get("match_dates") or (ev["date"],):
                try:
                    d_days = abs((datetime.fromisoformat(md[:10])
                                  - datetime.fromisoformat(ev_date[:10])).days)
                except ValueError:
                    d_days = 99999
                if d_days <= 5:
                    near = True
                    break
            if not near:
                continue
            a, b = ev["rate"], rate
            if a is None or b is None or max(abs(a), abs(b)) <= 0:
                continue
            if abs(a - b) / max(abs(a), abs(b)) <= 0.02:
                dup = True
                break
        if not dup:
            events.append(_norm_event("ddm", type_key, rate, ev_date, pay, r))

    events = [e for e in events if e["date"]]
    events.sort(key=lambda e: e["date"])
    _events_memo[tk] = (now, events)
    return events


def _sum_dividends_in_window(ticker: str, date_to: str, days: int = 365) -> float:
    """Sum merged per-share rates in the trailing N-day window (inclusive)."""
    try:
        date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
    except ValueError:
        return 0.0
    date_from = (date_to_dt - timedelta(days=days)).strftime("%Y-%m-%d")
    total = 0.0
    for ev in _merged_events(ticker):
        if ev["rate"] is None:
            continue
        if date_from <= ev["date"][:10] <= date_to:
            total += ev["rate"]
    return total


def _get_all_event_dates(ticker: str) -> list[str]:
    """All distinct dividend event dates (merged sources), oldest-first."""
    seen: set[str] = set()
    dates: list[str] = []
    for ev in _merged_events(ticker):
        d = ev["date"][:10]
        if d and d not in seen:
            seen.add(d)
            dates.append(d)
    return dates


@engine_cached
def dividends_at(ticker: str, date: str) -> float | None:
    """Get trailing twelve months dividends per share ending at or before date.

    DPA_TTM = SUM(rate WHERE event_date BETWEEN date-365 AND date)

    Where event_date = COALESCE(payment_date, last_date_prior, approved_on)
    for B3 rows and ex/record/payment for DDM rows (see module docstring).

    Args:
        ticker: B3 ticker (PETR4).
        date: YYYY-MM-DD.

    Returns:
        DPA TTM in BRL per share, or None if no dividends data.
        Returns 0.0 if the company pays no dividends (different from None
        which means "no data available").
    """
    total = _sum_dividends_in_window(ticker, date, days=365)
    if total == 0.0:
        # Distinguish "no data" from "company pays no dividends"
        event_dates = _get_all_event_dates(ticker)
        if not event_dates:
            return None  # No data at all
        # Check if there are any dividends BEFORE this date (company exists in DB)
        dates_before = [d for d in event_dates if d <= date]
        if not dates_before:
            return None  # No dividends before this date — can't compute TTM
        return 0.0  # Company exists but paid nothing in the window
    return total


@engine_cached
def dividends_periods(ticker: str) -> list[dict]:
    """Get all DPA TTM periods for a ticker.

    Returns: [{"date": "2024-06-30", "dpa": 1.85}, ...] sorted oldest-first.
    Each entry represents a point where DPA changed (a new dividend occurred).
    Between event dates, DPA is constant.

    Useful for building step-function DPA overlays on price charts.
    """
    event_dates = _get_all_event_dates(ticker)
    if not event_dates:
        return []

    periods = []
    for date in event_dates:
        dpa = dividends_at(ticker, date)
        if dpa is not None:
            periods.append({"date": date, "dpa": dpa})

    return periods


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="dividends",
    quantity="dpa",
    at_fn=dividends_at,
    periods_fn=dividends_periods,
    source="B3 cash_dividends (share-class corrected) ∪ DDM dividends agenda, event_date = COALESCE(payment_date, last_date_prior, approved_on)",
    category="market",
))
