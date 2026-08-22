"""data_sources/ddm/fluxo/status_reporter.py -- fluxo.db sync statistics.

Mirrors the ddm/focus status_reporter pattern: a single status() function
that returns DB path, size, row count, date range, and last-sync timestamp.
"""

from __future__ import annotations

from data_sources.ddm.fluxo.catalog import (
    connect, db_path,
)


def status() -> dict:
    """Show fluxo.db stats: row count + date range + last sync."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "fluxo.db not found. Run sync_all first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "fluxo.db not found."}

    try:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM fluxo_observations"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug='fluxo'"
        ).fetchone()

        range_row = conn.execute(
            "SELECT MIN(ref_date) as first_date, MAX(ref_date) as last_date "
            "FROM fluxo_observations"
        ).fetchone()

        return {
            "status":       "ok",
            "path":         str(path),
            "db_size_kb":   round(path.stat().st_size / 1024, 1),
            "total_rows":   total_rows,
            "first_date":   range_row["first_date"] if range_row else "",
            "last_date":    (sync_row["last_date"] if sync_row else
                             (range_row["last_date"] if range_row else "")),
            "last_sync":    sync_row["synced_at"] if sync_row else "",
            "synced_rows":  sync_row["row_count"] if sync_row else 0,
        }
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()
