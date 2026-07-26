"""data_sources/b3/cotahist/status_reporter.py -- COTAHIST sync statistics.

[v1.1] Split from query_engine.py to follow the CVM pattern (status_reporter.py
as a separate file). Same status() function, just in its own module.
"""
from __future__ import annotations

from data_sources.b3.cotahist.catalog import connect, db_path


def status() -> dict:
    """Show COTAHIST DB stats: years synced, row counts, date range."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "cotahist.db not found. Run sync first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "cotahist.db not found."}

    try:
        total = conn.execute("SELECT COUNT(*) as n FROM cotahist").fetchone()["n"]
        if total == 0:
            return {"status": "not_synced", "message": "cotahist.db exists but has no data. Run sync first."}

        # Date range
        min_date = conn.execute("SELECT MIN(refdate) as d FROM cotahist").fetchone()["d"]
        max_date = conn.execute("SELECT MAX(refdate) as d FROM cotahist").fetchone()["d"]

        # Distinct tickers
        tickers = conn.execute(
            "SELECT COUNT(DISTINCT symbol) as n FROM cotahist"
        ).fetchone()["n"]

        # Years synced
        years = conn.execute(
            "SELECT year, rows_added, synced_at, duration_s FROM sync_state ORDER BY year"
        ).fetchall()

        # DB size
        db_size_mb = round(path.stat().st_size / (1024 * 1024), 1)

        return {
            "status": "ok",
            "path": str(path),
            "db_size_mb": db_size_mb,
            "total_rows": total,
            "distinct_tickers": tickers,
            "date_range": {"from": min_date, "to": max_date},
            "years_synced": [
                {"year": y["year"], "rows": y["rows_added"],
                 "synced_at": y["synced_at"], "duration_s": y["duration_s"]}
                for y in years
            ],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()
