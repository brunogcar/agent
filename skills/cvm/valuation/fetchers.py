"""skills/cvm/valuation/fetchers.py -- Price data fetching (brapi/b3/cotahist).

Holds the internal price-fetching helpers consumed by modes/ratios.py. These
implement a 3-tier fallback chain for the current price (brapi -> b3
trades.db -> cotahist.db daily close) that is NOT covered by the calculations
price engine (which is COTAHIST-only and used for historical daily prices).

[v2.2] investsite REMOVED — investsite started forcing login (token
rotation), making it unreliable as an automated fallback. All
investsite-derived ratios (P/L, P/VPA, market_cap back-calculation for
UNIT tickers) are computed from market_cap + fundamentals instead.

[v2.3] COTAHIST 3rd tier ADDED — brapi auth failures (401 -> module-level
disable flag) made the 2-tier chain fail whenever trades.db is not synced.
cotahist.db holds the daily closes that power the price dashboard, so it is
always in sync — the latest market_type=10 close is a solid last resort.

Functions:
  - _get_price               : 3-tier dispatcher (brapi -> b3 trades -> cotahist).
  - _get_price_brapi         : brapi quote (also returns market_cap + pe_ratio).
  - _get_latest_price        : b3 trades.db fallback (most recent trade).
  - _get_price_cotahist      : cotahist.db fallback (latest daily close).
"""
from __future__ import annotations

from datetime import datetime


# ── Internal: get price (brapi -> b3 trades -> cotahist) ─────────────────────
# [v2.3] 3-tier fallback: the CURRENT price from brapi first, then b3
# trades.db, then the latest cotahist.db daily close. brapi also returns
# market_cap + pe_ratio for the ratios.py manual computations; the other
# two tiers return price only (market_cap falls back to price × shares).

def _get_price(ticker: str) -> dict:
    """3-tier price source: brapi -> b3 trades -> cotahist daily close."""
    brapi_data = _get_price_brapi(ticker)
    if brapi_data.get("status") == "ok":
        return brapi_data

    b3_data = _get_latest_price(ticker)
    if b3_data.get("status") == "ok":
        b3_data["source"] = "b3_trades"
        return b3_data

    cotahist_data = _get_price_cotahist(ticker)
    if cotahist_data.get("status") == "ok":
        return cotahist_data

    # All failed — return the brapi error (more informative than b3's)
    return brapi_data if brapi_data.get("status") == "error" else {
        "status": "error",
        "error": f"Price unavailable for {ticker} (brapi + b3 trades + cotahist all failed)",
    }


def _get_price_brapi(ticker: str) -> dict:
    try:
        from data_sources.b3.brapi.query_engine import quote as brapi_quote
        r = brapi_quote(ticker=ticker, force=True)
        if r.get("status") != "ok":
            return {"status": "error", "error": f"brapi: {r.get('error','')}"}
        price = r.get("price")
        if price is None:
            return {"status": "error", "error": "brapi: no price"}
        return {
            "status": "ok", "source": "brapi",
            "last_price": float(price),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "market_cap": r.get("market_cap"),
            "pe_ratio": r.get("pe_ratio"),
        }
    except Exception as e:
        return {"status": "error", "error": f"brapi: {e}"}


def _get_latest_price(ticker: str) -> dict:
    """Get latest price from b3 trades.db (fallback)."""
    try:
        import sqlite3
        from data_sources.b3.api.catalog import db_path as b3_db_path
        trades_db = b3_db_path("trades")
        if not trades_db.exists():
            return {"status": "not_synced", "error": "trades.db not found"}
        conn = sqlite3.connect(f"file:{trades_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT RptDt, LastPric FROM trades WHERE TckrSymb=? ORDER BY RptDt DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if not row:
            return {"status": "not_found", "error": f"No trades for {ticker}"}
        return {"status": "ok", "date": row["RptDt"],
                "last_price": float(row["LastPric"]) if row["LastPric"] else None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _get_price_cotahist(ticker: str) -> dict:
    """Get latest daily close from cotahist.db (3rd-tier fallback). [v2.3]

    cotahist.db powers the price dashboard (daily OHLCV since 2010), so it
    is always in sync. market_type=10 = equity spot (PVista). Mirrors
    _get_latest_price's shape: {status, date, last_price}.
    """
    try:
        import sqlite3
        from data_sources.b3.cotahist.catalog import db_path as cotahist_db_path
        db = cotahist_db_path()
        if not db.exists():
            return {"status": "not_synced", "error": "cotahist.db not found"}
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT refdate, close FROM cotahist "
            "WHERE symbol = ? AND market_type = 10 "
            "AND close IS NOT NULL AND close > 0 "
            "ORDER BY refdate DESC LIMIT 1",
            (ticker.strip().upper(),),
        ).fetchone()
        conn.close()
        if not row or not row["close"]:
            return {"status": "not_found", "error": f"No cotahist close for {ticker}"}
        return {"status": "ok", "source": "cotahist",
                "date": row["refdate"], "last_price": float(row["close"])}
    except Exception as e:
        return {"status": "error", "error": str(e)}
