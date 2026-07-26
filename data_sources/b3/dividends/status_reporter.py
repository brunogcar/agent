"""data_sources/b3/dividends/status_reporter.py -- B3 dividends sync statistics.

[v1.1] Split from query_engine.py to follow the CVM pattern (status_reporter.py
as a separate file). Same status() function, just in its own module.
"""
from __future__ import annotations

from data_sources.b3.dividends.catalog import connect, db_path


def status() -> dict:
    """Show sync status for all synced tickers."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced", "message": "Dividends database not found. Run sync first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "Dividends database not found."}

    try:
        cash_total = conn.execute("SELECT COUNT(*) as n FROM cash_dividends").fetchone()["n"]
        stock_total = conn.execute("SELECT COUNT(*) as n FROM stock_dividends").fetchone()["n"]
        sub_total = conn.execute("SELECT COUNT(*) as n FROM subscriptions").fetchone()["n"]

        synced = conn.execute(
            "SELECT * FROM sync_state ORDER BY synced_at DESC"
        ).fetchall()

        return {
            "status": "ok",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "totals": {"cash": cash_total, "stock": stock_total, "subscriptions": sub_total},
            "synced_tickers": [{
                "ticker": r["ticker"],
                "synced_at": r["synced_at"],
                "cash_count": r["cash_count"],
                "stock_count": r["stock_count"],
                "sub_count": r["sub_count"],
            } for r in synced],
        }
    except Exception:
        return {"status": "not_synced", "message": "DB exists but tables not created. Run sync first."}
    finally:
        conn.close()
