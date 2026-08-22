"""data_sources/ddm/focus/status_reporter.py -- focus.db sync statistics.

Mirrors the ddm/acoes status_reporter pattern: a single status() function
that returns DB path, size, row count, distinct year/indicator counts, and
last-sync timestamp.
"""

from __future__ import annotations

from data_sources.ddm.focus.catalog import (
    connect, db_path,
)


def status() -> dict:
    """Show focus.db stats: row count + year/indicator counts + last sync."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "focus.db not found. Run sync_all first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "focus.db not found."}

    try:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM focus_observations"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug='focus'"
        ).fetchone()

        year_rows = conn.execute(
            "SELECT DISTINCT year FROM focus_observations ORDER BY year ASC"
        ).fetchall()
        ind_rows = conn.execute(
            "SELECT DISTINCT indicator FROM focus_observations "
            "ORDER BY indicator ASC"
        ).fetchall()

        return {
            "status":           "ok",
            "path":             str(path),
            "db_size_kb":       round(path.stat().st_size / 1024, 1),
            "total_rows":       total_rows,
            "year_count":       len(year_rows),
            "indicator_count":  len(ind_rows),
            "years":            [r["year"] for r in year_rows],
            "indicators":       [r["indicator"] for r in ind_rows],
            "last_date":        sync_row["last_date"] if sync_row else "",
            "last_sync":        sync_row["synced_at"] if sync_row else "",
            "synced_rows":      sync_row["row_count"] if sync_row else 0,
        }
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()
