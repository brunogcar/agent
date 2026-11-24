"""webui/services/portfolio_perf.py — TWR/XIRR vs CDI/IBOV + the
patrimônio evolution curve.

[v1.22.3] Roadmap 4. Three numbers a serious investor asks ("am I
beating CDI?") and the picture behind them:

  - PATRIMÔNIO CURVE: the book replayed to every grid date (month ends
    + today) × the CLOSE of that date — per (account, ticker) the
    engine's own ladder gives the quantity held at any date (corp
    actions included), cotahist price_series gives the last close ≤
    that date. The same series feeds TWR (at every cashflow date).
  - XIRR (money-weighted): the tx cashflows (buys = −(q·p + taxas),
    sells = +(q·p − taxas)) + the current book value as the terminal
    inflow; the rate that zeroes the NPV, solved by bisection (the
    classic sign-change bracket; None + an honest note when it doesn't
    converge — e.g. an all-withdrawals book).
  - TWR (time-weighted): chained sub-period returns between cashflow
    dates — r_i = V(d_i) / (V(d_{i−1}) + CF(d_i)) − 1 (the cashflow
    lands end-of-day: it is inside V(d_i)); immune to deposit timing,
    the fair "how good were the decisions" number.
  - BENCHMARKS over the SAME window: CDI (sgs.db daily series 12 —
    % a.d. compounded per calendar trading day; the juros.db monthly
    series is the fallback) and IBOV proxied by BOVA11 (cotahist —
    the ETF tracks the index; when the paper is absent the payload
    names it and shows CDI only). Both annualized on the window's day
    count, same as TWR/XIRR.

Honesty notes shipped with the payload: shorts make the numbers
approximate (a negative book has no IRR meaning); the curve marks
partial months when a ticker has no quote before a grid date; CDI from
monthly fallback is a (1+r/100)^(1/252)-per-day derivation.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import date
from typing import Any

from tools.report_ops.formats import fmt_num

from webui.services.portfolio import portfolio_service
from webui.services.macro import _brl2, _fmt_date

# ── price maps (cotahist price_series, cached) ───────────────────────────────

_PX_TTL = 120.0                 # seconds a per-ticker price map stays cached
_px_cache: dict[str, tuple[float, list[str], list[float]]] = {}
_px_lock = threading.Lock()


def _price_map(ticker: str, date_from: str, date_to: str
               ) -> tuple[list[str], list[float]]:
    """(dates ASC, closes) for the ticker; ([], []) when unavailable."""
    hit = _px_cache.get(ticker)
    now = time.monotonic()
    if hit and now - hit[0] < _PX_TTL:
        return hit[1], hit[2]
    try:
        from skills.cvm.calculations.engines.price import price_series
        series = price_series(ticker, date_from, date_to) or []
    except Exception:
        series = []
    dates = [p["date"] for p in series]
    closes = [float(p["close"]) for p in series]
    with _px_lock:
        _px_cache[ticker] = (now, dates, closes)
    return dates, closes


def _last_close_le(dates: list[str], closes: list[float],
                   when: str) -> float | None:
    """Last close at or before ``when`` (None when nothing yet)."""
    if not dates:
        return None
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] <= when:
            lo = mid + 1
        else:
            hi = mid
    return closes[lo - 1] if lo > 0 else None


# ── CDI — sgs.db daily (code 12), juros.db monthly fallback ──────────────────

_cdi_lock = threading.Lock()
_cdi_cache: dict[str, tuple[float, list[tuple[str, float]]]] = {}


def _cdi_daily(date_from: str, date_to: str) -> list[tuple[str, float]]:
    """[(date, daily factor)] ASC — the compounding factors per day.

    Primary: sgs.db series 12 (CDI diária, % a.d. — factor =
    1 + value/100 per day). Fallback: juros.db monthly CDI →
    (1 + r/100)^(1/252) per calendar day of the month.
    """
    key = f"{date_from}|{date_to}"
    hit = _cdi_cache.get(key)
    if hit and time.monotonic() - hit[0] < _PX_TTL:
        return hit[1]
    out: list[tuple[str, float]] = []
    try:
        from data_sources.bcb.sgs.query_engine import series as sgs_series
        res = sgs_series(12, start=date_from, end=date_to)
        if res.get("status") == "ok":
            out = [(o["ref_date"], 1.0 + float(o["value"]) / 100.0)
                   for o in res.get("observations", []) if o.get("ref_date")]
    except Exception:
        out = []
    if not out:
        try:
            from skills.ddm.juros.history import juros_history
            res = juros_history(slug="cdi", limit=0)
            if res.get("status") == "ok":
                monthly = {o["ref_date"]: float(o["month_value"])
                           for o in res.get("observations", [])
                           if o.get("ref_date") and o.get("month_value")}
                from datetime import timedelta
                d = date.fromisoformat(date_from)
                end = date.fromisoformat(date_to)
                while d <= end:
                    m = monthly.get(d.isoformat()[:7])
                    if m is not None:
                        out.append((d.isoformat(),
                                    (1.0 + m / 100.0) ** (1.0 / 252.0)))
                    d += timedelta(days=1)
        except Exception:
            out = []
    with _cdi_lock:
        _cdi_cache[key] = (time.monotonic(), out)
    return out


# ── helpers ──────────────────────────────────────────────────────────────────

def _scope_accounts(snap: dict, scope: str) -> list[dict]:
    if scope.startswith("user:"):
        uid = scope[5:]
        return [a for a in snap["accounts"] if a.get("user_id") == uid]
    if scope.startswith("account:"):
        aid = scope[8:]
        return [a for a in snap["accounts"] if a.get("id") == aid]
    return list(snap["accounts"])


def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date.fromordinal(date(d.year, d.month + 1, 1).toordinal() - 1)


def _brl(v: float | None) -> str | None:
    return _brl2(v) if v is not None else None


def _pct(v: float | None) -> str | None:
    """0.1234 → '12,34%' (annualized returns as ratios)."""
    if v is None:
        return None
    return fmt_num(v * 100.0, decimals=2) + "%"


def _xirr(flows: list[tuple[str, float]], end_date: str) -> float | None:
    """Annualized rate zeroing the NPV (bisection, 240 iterations).

    flows: [(iso date, amount)] — deposits negative, withdrawals and
    the terminal value positive. None when the bracket has no sign
    change (no solution in [-99,9%, +1000%]).
    """
    if not flows:
        return None
    t0 = date.fromisoformat(min(f[0] for f in flows))
    days = [(date.fromisoformat(d) - t0).days for d, _ in flows]
    amounts = [a for _, a in flows]

    def npv(rate: float) -> float:
        return math.fsum(a / (1.0 + rate) ** (t / 365.0)
                         for a, t in zip(amounts, days))

    lo, hi = -0.999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(240):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


# ── the report ───────────────────────────────────────────────────────────────

def performance_report(scope: str) -> dict[str, Any]:
    """The 📈 Evolução view: curve + XIRR/TWR + benchmarks."""
    svc = portfolio_service()
    snap = svc._snapshot()
    accounts = _scope_accounts(snap, scope)
    if not snap["users"]:
        return {"ok": True, "empty": "no_users"}
    if not accounts:
        return {"ok": True, "empty": "no_accounts"}
    account_ids = {a["id"] for a in accounts}
    txs = [t for t in snap["txs"] if t.get("account_id") in account_ids]
    if not txs:
        return {"ok": True, "empty": "no_txs"}

    today = date.today().isoformat()
    first_date = min(t.get("date") or today for t in txs)

    # Per (account, ticker): the engine ladder + its date column; the
    # price map for the ticker (window padded to the month start for
    # the last-close-≤-date lookups).
    tickers: set[str] = set()
    for t in txs:
        if t.get("ticker"):
            tickers.add(t["ticker"])
    ladders: list[dict[str, Any]] = []
    for acc in accounts:
        acc_txs = [t for t in txs if t.get("account_id") == acc["id"]]
        if not acc_txs:
            continue
        for tk in sorted(tickers):
            rows = svc._ticker_ladder(acc_txs, tk)
            if rows:
                ladders.append({"ticker": tk, "rows": rows,
                                "dates": [r["date"] for r in rows]})

    px_from = first_date[:8] + "01"
    prices: dict[str, tuple[list[str], list[float]]] = {}
    missing_px: list[str] = []
    for tk in sorted(tickers):
        pm = _price_map(tk, px_from, today)
        prices[tk] = pm
        if not pm[0]:
            missing_px.append(tk)

    def value_at(when: str) -> tuple[float, bool]:
        """Book value at close of ``when`` (+ completeness flag)."""
        total = 0.0
        complete = True
        for l in ladders:
            rows, dates = l["rows"], l["dates"]
            # quantity held after every tx dated ≤ when
            i = _bisect_right_str(dates, when)
            if i == 0:
                continue
            qty = rows[i - 1]["run_qty"]
            if abs(qty) < 1e-9:
                continue
            dates_px, closes_px = prices.get(l["ticker"], ([], []))
            px = _last_close_le(dates_px, closes_px, when)
            if px is None:
                complete = False
                continue
            total += px * qty
        return total, complete

    # Cashflows by date (investor perspective: in = buy cost, out =
    # sell proceeds — CF(d) is the money that ENTERED the book on d).
    cf_by_date: dict[str, float] = {}
    for t in txs:
        d = t.get("date") or ""
        if not d or t.get("type") == "corp":
            continue
        q = float(t.get("quantity") or 0.0)
        p = float(t.get("price") or 0.0)
        fees = float(t.get("fees") or 0.0)
        if t.get("type") == "buy":
            cf_by_date[d] = cf_by_date.get(d, 0.0) + (q * p + fees)
        else:
            cf_by_date[d] = cf_by_date.get(d, 0.0) - (q * p - fees)

    tx_dates = sorted(cf_by_date)

    # ── TWR: chained between cashflow dates ──
    # Convention: the cashflow executes AT the day's close (the bought
    # shares sit in V(d) at that day's price — they earned nothing on
    # their own entry day), so r_i = (V(d_i) − CF(d_i)) / V(d_{i−1}) − 1.
    # Verified: buy 100@10 → sell 50@12 gives (600−(−600))/1000 − 1 =
    # +20% — exactly the market move of the held book, timing-free.
    twr_total: float | None = None
    twr_annual: float | None = None
    partial = False
    if len(tx_dates) >= 1:
        chain = 1.0
        prev_v: float | None = None
        for i, d in enumerate(tx_dates):
            v, comp = value_at(d)
            if not comp:
                partial = True
            if i == 0 or prev_v is None or abs(prev_v) < 1e-9:
                prev_v = v
                continue
            denom = prev_v
            numer = v - cf_by_date[d]
            if abs(denom) > 1e-9:
                chain *= numer / denom
            prev_v = v
        # final leg to today (no cashflow assumed after the last tx date)
        if tx_dates and tx_dates[-1] < today:
            v_end, comp = value_at(today)
            if not comp:
                partial = True
            if prev_v is not None and abs(prev_v) > 1e-9:
                chain *= v_end / prev_v
        twr_total = chain - 1.0
        days = (date.fromisoformat(today) -
                date.fromisoformat(first_date)).days
        if days > 0:
            twr_annual = (1.0 + twr_total) ** (365.0 / days) - 1.0

    # ── XIRR ──
    flows: list[tuple[str, float]] = []
    for d in tx_dates:
        # money that entered the book is a NEGATIVE flow (deposit)
        flows.append((d, -cf_by_date[d]))
    final_value, comp_final = value_at(today)
    if not comp_final:
        partial = True
    xirr = None
    if flows and final_value != 0.0:
        flows.append((today, final_value))
        xirr = _xirr(flows, today)

    # ── benchmarks over the same window ──
    cdi = _cdi_daily(first_date, today)
    cdi_total = None
    if cdi:
        cdi_total = 1.0
        for _d, f in cdi:
            cdi_total *= f
        cdi_total -= 1.0
    days = (date.fromisoformat(today) -
            date.fromisoformat(first_date)).days
    cdi_annual = ((1.0 + cdi_total) ** (365.0 / days) - 1.0
                  if cdi_total is not None and days > 0 else None)

    ibov_dates, ibov_closes = _price_map("BOVA11", px_from, today)
    ibov_total = None
    if ibov_dates:
        start_px = _last_close_le(ibov_dates, ibov_closes, first_date)
        end_px = _last_close_le(ibov_dates, ibov_closes, today)
        if start_px and start_px > 0 and end_px:
            ibov_total = end_px / start_px - 1.0
    ibov_annual = ((1.0 + ibov_total) ** (365.0 / days) - 1.0
                   if ibov_total is not None and days > 0 else None)

    # ── the curve grid: month ends + today ──
    grid: list[str] = []
    d0 = date.fromisoformat(first_date)
    cur = d0
    while True:
        grid.append(_month_end(cur).isoformat())
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
        if cur > date.today():
            break
    grid.append(today)
    grid = sorted(set(g for g in grid if first_date <= g <= today))

    curve_labels: list[str] = []
    curve_pat: list[float] = []
    curve_cdi: list[float | None] = []
    curve_ibov: list[float | None] = []
    pat0 = None
    for g in grid:
        v, comp = value_at(g)
        if not comp:
            partial = True
        if pat0 is None and abs(v) > 1e-9:
            pat0 = v
        if pat0 is None:
            continue
        curve_labels.append(g)
        curve_pat.append(round(v, 2))
        if cdi:
            # CDI accumulated from the curve's first point
            acc = 1.0
            for dd, f in cdi:
                if dd > g:
                    break
                if dd >= curve_labels[0]:
                    acc *= f
            curve_cdi.append(round(pat0 * acc, 2))
        else:
            curve_cdi.append(None)
        if ibov_dates and ibov_total is not None:
            base = _last_close_le(ibov_dates, ibov_closes, curve_labels[0])
            px = _last_close_le(ibov_dates, ibov_closes, g)
            if base and px:
                curve_ibov.append(round(pat0 * px / base, 2))
            else:
                curve_ibov.append(None)
        else:
            curve_ibov.append(None)

    has_short = any(
        abs(l["rows"][-1]["run_qty"]) > 1e-9 and l["rows"][-1]["run_qty"] < 0
        for l in ladders if l["rows"])

    kpis = [
        {"label": "Retorno total (TWR)", "value": _pct(twr_total),
         "tooltip": "Retorno ponderado pelo tempo — encadeia os retornos "
                    "entre cada movimentação; imune ao timing dos aportes."},
        {"label": "TWR anualizado", "value": _pct(twr_annual),
         "tooltip": "O retorno total anualizado pelo período em dias."},
        {"label": "XIRR (dinheiro)", "value": _pct(xirr),
         "tooltip": "Retorno ponderado pelo dinheiro — a taxa que zera o "
                    "valor presente dos fluxos (compras negativas, vendas "
                    "e o valor atual positivo)."},
        {"label": "CDI no período",
         "value": _pct(cdi_total),
         "tooltip": "CDI acumulado no mesmo intervalo (fonte: BCB SGS "
                    "série 12, taxa diária)."},
        {"label": "CDI anualizado", "value": _pct(cdi_annual), "tooltip":
         "O acumulado do CDI anualizado pelo período em dias."},
        {"label": "IBOV (via BOVA11)", "value": _pct(ibov_total),
         "tooltip": "Provento do BOVA11 (ETF que replica o Ibovespa) no "
                    "mesmo intervalo — proxy do índice."},
    ]
    if ibov_total is not None:
        kpis.append({"label": "IBOV anualizado", "value": _pct(ibov_annual),
                     "tooltip": "O retorno do BOVA11 anualizado."})

    notes = [
        "Janela: " + _fmt_date(first_date) + " → " + _fmt_date(today)
        + f" ({days} dias).",
        "XIRR usa os fluxos das transações + o valor atual da carteira; "
        "TWR encadeia os retornos entre movimentações (cashflow no fim "
        "do dia).",
        "IBOV aproximado pelo BOVA11 (ETF) — o índice em si não tem "
        "série no cotahist.",
    ]
    if has_short:
        notes.append("⚠️ Há posição vendida a descoberto aberta — TWR/XIRR "
                     "são aproximações (patrimônio negativo não tem taxa "
                     "interna de retorno bem definida).")
    if missing_px:
        notes.append("⚠️ Sem histórico de preços para "
                     + ", ".join(missing_px)
                     + " — os períodos antes da primeira cotação ficam "
                       "incompletos.")
    if partial:
        notes.append("⚠️ Alguns pontos da curva não têm cotação para todos "
                     "os ativos (papel ilíquido) — valores parciais.")
    if not cdi:
        notes.append("CDI indisponível — sincronize a fonte sgs (BCB) na "
                     "página Sincronização.")

    return {
        "ok": True,
        "empty": None,
        "from": first_date,
        "to": today,
        "days": days,
        "kpis": kpis,
        "xirr": xirr,
        "twr_total": twr_total,
        "twr_annual": twr_annual,
        "cdi_total": cdi_total,
        "cdi_annual": cdi_annual,
        "ibov_total": ibov_total,
        "ibov_annual": ibov_annual,
        "curve": {
            "labels": curve_labels,
            "patrimonio": curve_pat,
            "cdi": curve_cdi,
            "ibov": curve_ibov,
        },
        "final_value_br": _brl(final_value),
        "notes": notes,
    }


def _bisect_right_str(dates: list[str], when: str) -> int:
    """bisect.bisect_right for a sorted ISO-date list (local, no import
    drift — the stdlib bisect is used elsewhere; this keeps the module
    import-light for the common path)."""
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] <= when:
            lo = mid + 1
        else:
            hi = mid
    return lo
