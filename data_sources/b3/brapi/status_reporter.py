"""data_sources/b3/brapi/status_reporter.py -- brapi.dev sync statistics.

[v1.1] Split from query_engine.py to follow the CVM pattern (status_reporter.py
as a separate file). Same status() function, just in its own module.
"""
from __future__ import annotations

from data_sources.b3.brapi.catalog import connect, db_path


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
