"""data_sources/b3/brapi/query_engine.py -- Query brapi.db for prices + tickers.

Read-only queries against brapi.db:
  - quote(ticker) — latest price from cache or live fetch
  - history(ticker, days) — historical OHLCV from local DB
  - tickers() — list all synced tickers
  - status() — brapi.db stats
"""

from __future__ import annotations

from datetime import datetime, timezone

from data_sources.b3.brapi.catalog import connect, db_path
from data_sources.b3.brapi.fetcher import fetch_quote


def quote(ticker: str = "", force: bool = False) -> dict:
    """Get the latest quote for a ticker.

    Tries local DB first (if synced today), then fetches live from brapi.dev.

    Args:
        ticker: B3 ticker (PETR4).
        force: Always fetch live (skip local DB).

    Returns:
        Dict with price, market_cap, pe, volume, etc.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()

    # Try local DB first (unless force)
    if not force:
        try:
            conn = connect(read_only=True)
            row = conn.execute(
                "SELECT * FROM quotes WHERE symbol=? ORDER BY date DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            conn.close()
            if row:
                return {
                    "status": "ok",
                    "ticker": ticker,
                    "source": "local",
                    "date": row["date"],
                    "price": row["close"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "volume": row["volume"],
                }
        except FileNotFoundError:
            pass  # DB not synced — fall through to live

    # Fetch live from brapi.dev
    result = fetch_quote(ticker, force=force)
    if result.get("status") != "ok":
        return result

    q = result["quote"]
    return {
        "status": "ok",
        "ticker": ticker,
        "source": "brapi_live",
        "price": q.get("regularMarketPrice"),
        "open": q.get("regularMarketOpen"),
        "high": q.get("regularMarketDayHigh"),
        "low": q.get("regularMarketDayLow"),
        "volume": q.get("regularMarketVolume"),
        "market_cap": q.get("marketCap"),
        "pe_ratio": q.get("priceEarnings"),
        "eps": q.get("earningsPerShare"),
        "52week_range": q.get("fiftyTwoWeekRange"),
        "currency": q.get("currency"),
    }


def history(ticker: str = "", days: int = 30) -> dict:
    """Query historical OHLCV from local DB.

    Args:
        ticker: B3 ticker (PETR4).
        days: Number of days of history. Default: 30.

    Returns:
        Dict with OHLCV list.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close, adjusted_close, volume "
            "FROM quotes WHERE symbol=? "
            "ORDER BY date DESC LIMIT ?",
            (ticker, days),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "ticker": ticker,
                    "error": f"No history for {ticker}. Run sync_history first."}

        return {
            "status": "ok",
            "ticker": ticker,
            "count": len(rows),
            "ohlcv": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def tickers() -> dict:
    """List all synced tickers."""
    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        rows = conn.execute("SELECT symbol FROM tickers ORDER BY symbol").fetchall()
        return {
            "status": "ok",
            "count": len(rows),
            "tickers": [r["symbol"] for r in rows],
        }
    finally:
        conn.close()


def status() -> dict:
    """Show brapi.db stats."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "brapi.db not found. Run sync first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "brapi.db not found."}

    try:
        ticker_count = conn.execute("SELECT COUNT(*) as n FROM tickers").fetchone()["n"]
        quote_count = conn.execute("SELECT COUNT(*) as n FROM quotes").fetchone()["n"]
        symbols = conn.execute(
            "SELECT COUNT(DISTINCT symbol) as n FROM quotes"
        ).fetchone()["n"]

        last_sync = conn.execute(
            "SELECT value, synced_at FROM sync_state WHERE key='tickers'"
        ).fetchone()

        return {
            "status": "ok",
            "path": str(path),
            "db_size_kb": round(path.stat().st_size / 1024, 1),
            "tickers": ticker_count,
            "ohlcv_rows": quote_count,
            "symbols_with_history": symbols,
            "last_ticker_sync": last_sync["synced_at"] if last_sync else "",
        }
    except Exception:
        return {"status": "not_synced", "message": "DB exists but tables not created."}
    finally:
        conn.close()
