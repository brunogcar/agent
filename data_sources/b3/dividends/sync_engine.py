"""data_sources/b3/dividends/sync_engine.py -- Sync B3 dividends for a ticker.

Per-ticker JSON API (not paginated). Downloads cash dividends, stock
dividends, and subscription rights for a single company.

Flow:
  1. Build base64 params from ticker (first 4 chars = issuing company)
  2. GET API → JSON with cashDividends, stockDividends, subscriptions
  3. Parse + normalize dates (DD/MM/YYYY → YYYY-MM-DD)
  4. DELETE old data for this ticker + INSERT new
  5. Record sync_state
"""

from __future__ import annotations

import base64
import json
import sqlite3
import sys
import time
from datetime import datetime
from typing import Any

import httpx

from core.tracer import tracer
from data_sources.b3.dividends.catalog import API_BASE, connect, ensure_schema


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def sync(
    ticker: str = "",
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download and store dividends data for a specific ticker.

    Args:
        ticker: Full ticker (e.g., "PETR4"). First 4 chars = issuing company.
        force: Re-download even if already synced.
        trace_id: Tracer ID.

    Returns:
        Dict with sync status + row counts per table.
    """
    tid = trace_id or ""
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    issuing = ticker[:4]

    conn = connect(read_only=False)
    ensure_schema(conn)

    # Skip if already synced (unless force)
    if not force:
        existing = conn.execute(
            "SELECT * FROM sync_state WHERE ticker=?", (ticker,),
        ).fetchone()
        if existing:
            return {
                "status": "skipped",
                "ticker": ticker,
                "cash_count": existing["cash_count"],
                "stock_count": existing["stock_count"],
                "sub_count": existing["sub_count"],
                "synced_at": existing["synced_at"],
            }

    # Build API URL
    params = {"issuingCompany": issuing, "language": "pt-br"}
    b64 = base64.b64encode(json.dumps(params, separators=(",", ":")).encode()).decode()
    url = f"{API_BASE}/{b64}"

    tracer.step(tid, "b3_div_sync", f"Downloading dividends for {ticker}")
    _progress(f"[b3_div] Fetching {ticker}...")

    try:
        resp = httpx.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        resp.raise_for_status()
    except Exception as e:
        conn.close()
        return {"status": "error", "ticker": ticker, "error": f"API request failed: {e}"}

    # Parse response — B3 returns a JSON string (not auto-parsed by httpx sometimes)
    try:
        data = resp.json()
        if isinstance(data, str):
            data = json.loads(data)
    except Exception:
        conn.close()
        return {"status": "error", "ticker": ticker, "error": "Invalid JSON response"}

    if not isinstance(data, list) or not data:
        conn.close()
        return {"status": "empty", "ticker": ticker, "error": "No dividend data for this ticker"}

    item = data[0]
    now = datetime.now().isoformat()

    # Store company info (codeCVM links to CVM cad.db!)
    company_count = _store_company_info(conn, item, ticker, now)

    # Parse + store each table
    cash_count = _store_cash_dividends(conn, item.get("cashDividends", []), ticker, now)
    stock_count = _store_stock_dividends(conn, item.get("stockDividends", []), ticker, now)
    sub_count = _store_subscriptions(conn, item.get("subscriptions", []), ticker, now)

    # Record sync state
    conn.execute(
        "INSERT OR REPLACE INTO sync_state (ticker, synced_at, cash_count, stock_count, sub_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticker, now, cash_count, stock_count, sub_count),
    )
    conn.commit()
    conn.close()

    _progress(f"[b3_div] {ticker}: {cash_count} cash, {stock_count} stock, {sub_count} subscriptions")

    return {
        "status": "ok",
        "ticker": ticker,
        "cash_count": cash_count,
        "stock_count": stock_count,
        "sub_count": sub_count,
        "synced_at": now,
    }


# ── Bulk sync (WebUI painel) [v1.5 fix1] ────────────────────────────────────

def _tracked_tickers() -> list[str]:
    """Tickers already tracked in dividends.db (from sync_state)."""
    try:
        conn = connect(read_only=True)
        rows = conn.execute(
            "SELECT ticker FROM sync_state ORDER BY ticker"
        ).fetchall()
        conn.close()
        return [r["ticker"] for r in rows if r["ticker"]]
    except Exception:
        return []


def _acoes_tickers() -> list[str]:
    """Seed list: every B3 tradable ticker from acoes.db (~380 rows).

    Used ONLY when sync_state is empty (fresh install) so the painel
    button does something useful on day one instead of no-op'ing.
    """
    try:
        from data_sources.ddm.acoes.catalog import db_path as acoes_db_path
        p = acoes_db_path()
        if not p.exists():
            return []
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        rows = conn.execute("SELECT ticker FROM stocks ORDER BY ticker").fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def sync_all(
    force: bool = True,
    trace_id: str = "",
    on_progress=None,
) -> dict:
    """[v1.5 fix1] Re-fetch dividends for every tracked ticker.

    The painel can't pass a company, and sync() without a ticker is a
    hard error — which the old dispatch silently reported as success
    (the row stayed "desatualizado" forever). This bulk entry point:

      1. Targets = tickers in sync_state (seeded from acoes.db when the
         table is empty).
      2. Re-fetches each (force=True default — freshness comes from the
         LAST sync_state row, so a no-op run must still write rows).
      3. Reports per-ticker progress via the optional on_progress
         callback: {"ticker", "status", "done", "total"}.

    Returns {"status": "ok"|"error", "total", "ok", "errors", ...}.
    """
    targets = _tracked_tickers()
    seeded = False
    if not targets:
        targets = _acoes_tickers()
        seeded = bool(targets)

    if not targets:
        return {
            "status": "ok", "total": 0, "ok": 0, "errors": 0,
            "detail": "nenhum ticker rastreado (abra uma empresa para "
                      "sincronizar dividends sob demanda)",
        }

    ok = errors = 0
    # Polite spacing for big sets (first-run acoes seed ≈ 380 calls).
    pace = 0.1 if len(targets) > 25 else 0.0
    _progress(f"[b3_div] sync_all: {len(targets)} tickers"
              f"{' (seeded from acoes.db)' if seeded else ''}...")

    for i, tkr in enumerate(targets, 1):
        r = sync(ticker=tkr, force=force, trace_id=trace_id)
        st = r.get("status")
        # "empty" (no dividend data for the ticker) is a valid answer,
        # not a failure — the API was consulted and answered.
        if st in ("ok", "skipped", "empty"):
            ok += 1
        else:
            errors += 1
        if on_progress is not None:
            try:
                on_progress({"ticker": tkr, "status": st, "done": i,
                             "total": len(targets)})
            except Exception:
                pass
        if pace and i < len(targets):
            time.sleep(pace)

    _progress(f"[b3_div] sync_all done: {ok} ok, {errors} errors")
    return {
        "status": "ok" if errors < len(targets) else "error",
        "total": len(targets),
        "ok": ok,
        "errors": errors,
        "seeded": seeded,
    }


def _normalize_date(date_str: str | None) -> str | None:
    """Convert DD/MM/YYYY -> YYYY-MM-DD."""
    if not date_str:
        return None
    v = str(date_str).strip()
    if not v:
        return None
    parts = v.split("/")
    if len(parts) != 3:
        return None
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, IndexError):
        return None


def _parse_rate(val: str | None) -> float | None:
    """Parse BRL rate — B3 uses comma as decimal separator."""
    if not val:
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _store_company_info(conn, item, ticker, now) -> int:
    """Store company info from the API response (codeCVM, shares, capital, etc.)."""
    conn.execute(
        "INSERT OR REPLACE INTO company_info "
        "(ticker, issuing_company, code_cvm, trading_name, segment, stock_capital, "
        "number_common_shares, number_preferred_shares, total_number_shares, "
        "round_lot, quoted_per_share_since, has_common, has_preferred, "
        "common_shares_form, preferred_shares_form, _ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ticker,
         (item.get("code") or "").strip(),
         (item.get("codeCVM") or "").strip(),
         (item.get("tradingName") or "").strip(),
         (item.get("segment") or "").strip(),
         (item.get("stockCapital") or "").strip(),
         (item.get("numberCommonShares") or "").strip(),
         (item.get("numberPreferredShares") or "").strip(),
         (item.get("totalNumberShares") or "").strip(),
         (item.get("roundLot") or "").strip(),
         _normalize_date(item.get("quotedPerSharSince")),
         (item.get("hasCommom") or "").strip(),
         (item.get("hasPreferred") or "").strip(),
         (item.get("commonSharesForm") or "").strip(),
         (item.get("preferredSharesForm") or "").strip(),
         now),
    )
    return 1


def _store_cash_dividends(conn, items, ticker, now) -> int:
    conn.execute("DELETE FROM cash_dividends WHERE ticker=?", (ticker,))
    count = 0
    for item in items:
        isin = (item.get("assetIssued") or "").strip()  # B3 uses assetIssued for ISIN in cash dividends
        approved = _normalize_date(item.get("approvedOn"))
        if not isin or not approved:
            continue
        conn.execute(
            "INSERT INTO cash_dividends (ticker, label, isin_code, approved_on, last_date_prior, rate, related_to, payment_date, remarks, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticker,
             (item.get("label") or "").strip(),
             isin,
             approved,
             _normalize_date(item.get("lastDatePrior")),
             _parse_rate(item.get("rate")),
             (item.get("relatedTo") or "").strip(),
             _normalize_date(item.get("paymentDate")),
             (item.get("remarks") or "").strip(),
             now),
        )
        count += 1
    return count


def _store_stock_dividends(conn, items, ticker, now) -> int:
    conn.execute("DELETE FROM stock_dividends WHERE ticker=?", (ticker,))
    count = 0
    for item in items:
        isin = (item.get("isinCode") or item.get("assetIssued") or "").strip()
        approved = _normalize_date(item.get("approvedOn"))
        if not isin or not approved:
            continue
        conn.execute(
            "INSERT INTO stock_dividends (ticker, label, isin_code, approved_on, last_date_prior, factor, asset_issued, remarks, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticker,
             (item.get("label") or "").strip(),
             isin,
             approved,
             _normalize_date(item.get("lastDatePrior")),
             _parse_rate(item.get("factor")),
             (item.get("assetIssued") or "").strip(),
             (item.get("remarks") or "").strip(),
             now),
        )
        count += 1
    return count


def _store_subscriptions(conn, items, ticker, now) -> int:
    conn.execute("DELETE FROM subscriptions WHERE ticker=?", (ticker,))
    count = 0
    for item in items:
        isin = (item.get("isinCode") or item.get("assetIssued") or "").strip()
        approved = _normalize_date(item.get("approvedOn"))
        if not isin or not approved:
            continue
        conn.execute(
            "INSERT INTO subscriptions (ticker, label, isin_code, approved_on, last_date_prior, percentage, asset_issued, price_unit, subscription_date, trading_period, remarks, _ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticker,
             (item.get("label") or "").strip(),
             isin,
             approved,
             _normalize_date(item.get("lastDatePrior")),
             _parse_rate(item.get("percentage")),
             (item.get("assetIssued") or "").strip(),
             _parse_rate(item.get("priceUnit")),
             _normalize_date(item.get("subscriptionDate")),
             (item.get("tradingPeriod") or "").strip(),
             (item.get("remarks") or "").strip(),
             now),
        )
        count += 1
    return count
