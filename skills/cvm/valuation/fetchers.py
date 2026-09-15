"""skills/cvm/valuation/fetchers.py -- Price data fetching (brapi/b3).

Holds the internal price-fetching helpers consumed by modes/ratios.py. These
implement a 2-tier fallback chain for the current price (brapi -> b3
trades.db) that is NOT covered by the calculations price engine (which
is COTAHIST-only and used for historical daily prices).

[v2.2] investsite REMOVED — investsite started forcing login (token
rotation), making it unreliable as an automated fallback. The price
chain is now brapi -> b3 trades only. All investsite-derived ratios
(P/L, P/VPA, market_cap back-calculation for UNIT tickers) are computed
from market_cap + fundamentals instead.

Functions:
  - _get_price               : 2-tier dispatcher (brapi -> b3 trades).
  - _get_price_brapi         : brapi quote (also returns market_cap + pe_ratio).
  - _get_latest_price         : b3 trades.db fallback (most recent trade).
"""
from __future__ import annotations

from datetime import datetime


# ── Internal: get price (brapi -> b3 trades) ────────────────────────────────
# [v2.2] investsite removed from the chain — login requirement made it
# unreliable. The 2-tier fallback gets the CURRENT price from brapi first,
# then b3 trades.db. brapi also returns market_cap + pe_ratio for the
# ratios.py manual computations.

def _get_price(ticker: str) -> dict:
    """2-tier price source: brapi -> b3 trades."""
    brapi_data = _get_price_brapi(ticker)
    if brapi_data.get("status") == "ok":
        return brapi_data

    b3_data = _get_latest_price(ticker)
    if b3_data.get("status") == "ok":
        b3_data["source"] = "b3_trades"
        return b3_data

    # Both failed — return the brapi error (more informative than b3's)
    return brapi_data if brapi_data.get("status") == "error" else {
        "status": "error",
        "error": f"Price unavailable for {ticker} (brapi + b3 both failed)",
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
