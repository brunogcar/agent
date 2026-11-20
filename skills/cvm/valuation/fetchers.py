"""skills/cvm/valuation/fetchers.py -- Price data fetching (b3/cotahist).

Holds the internal price-fetching helpers consumed by modes/ratios.py. These
implement a 2-tier fallback chain for the current price (b3 trades.db ->
cotahist.db daily close) that is NOT covered by the calculations price
engine (which is COTAHIST-only and used for historical daily prices).

[v2.2] investsite REMOVED — investsite started forcing login (token
rotation), making it unreliable as an automated fallback. All
investsite-derived ratios (P/L, P/VPA, market_cap back-calculation for
UNIT tickers) are computed from market_cap + fundamentals instead.

[v2.3] COTAHIST 3rd tier ADDED — brapi auth failures (401 -> module-level
disable flag) made the 2-tier chain fail whenever trades.db is not synced.
cotahist.db holds the daily closes that power the price dashboard, so it is
always in sync — the latest market_type=10 close is a solid last resort.

[v2.4] brapi REMOVED — brapi depends on a paid API key (401 without it),
so the tier is deleted entirely. Chain is now strictly local:
b3 trades.db -> cotahist.db. market_cap is ALWAYS computed as
price x total_shares by the caller (modes/ratios.py).

Functions:
  - _get_price               : 2-tier dispatcher (b3 trades -> cotahist).
  - _get_latest_price        : b3 trades.db fallback (most recent trade).
  - _get_price_cotahist      : cotahist.db fallback (latest daily close).
"""
from __future__ import annotations

from datetime import datetime


# ── Internal: get price (b3 trades -> cotahist) ─────────────────────────────
# [v2.4] 2-tier fallback: the CURRENT price from b3 trades.db first (most
# recent trade), then the latest cotahist.db daily close. Neither tier
# returns market_cap — the caller computes it as price x total_shares.

def _get_price(ticker: str) -> dict:
    """2-tier price source: b3 trades -> cotahist daily close.

    [WebUI v1.5] brapi tier removed (paid API, permanently disabled).
    """
    b3_data = _get_latest_price(ticker)
    if b3_data.get("status") == "ok":
        b3_data["source"] = "b3_trades"
        return b3_data

    cotahist_data = _get_price_cotahist(ticker)
    if cotahist_data.get("status") == "ok":
        return cotahist_data

    # All failed — return the b3 error (more informative than cotahist's)
    return b3_data if b3_data.get("status") == "error" else {
        "status": "error",
        "error": f"Price unavailable for {ticker} (b3 trades + cotahist failed)",
    }


def _get_latest_price(ticker: str) -> dict:
    """Get latest price from b3 trades.db (primary tier)."""
    try:
        import sqlite3
        from data_sources.b3.api.catalog import db_path as b3_db_path
        trades_db = b3_db_path("trades")
        if not trades_db.exists():
            return {"status": "not_synced", "error": "trades.db not found"}
        conn = sqlite3.connect(f"file:{trades_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT RptDt, LastPric FROM trades WHERE TckrSymb=? AND LastPric IS NOT NULL AND LastPric > 0 ORDER BY RptDt DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if not row:
            return {"status": "not_found", "error": f"No trades for {ticker}"}
        # [WebUI v1.5] LastPric NULL/0 rows are filtered in SQL — a missing
        # price can no longer return status "ok" with last_price None
        # (which poisoned downstream ratio math).
        return {"status": "ok", "date": row["RptDt"], "last_price": float(row["LastPric"])}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _get_price_cotahist(ticker: str) -> dict:
    """Get latest daily close from cotahist.db (2nd-tier fallback). [v2.3]

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
