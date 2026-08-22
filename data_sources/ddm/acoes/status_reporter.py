"""data_sources/ddm/acoes/status_reporter.py -- acoes.db sync statistics.

Mirrors the ddm/inflation + ddm/juros + ddm/poupanca status_reporter pattern:
a single status() function that returns DB path, size, row count, and
last-sync timestamp.
"""

from __future__ import annotations

from data_sources.ddm.acoes.catalog import (
    connect, db_path,
)


def status() -> dict:
    """Show acoes.db stats: row count + last sync timestamp."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "acoes.db not found. Run sync_all first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "acoes.db not found."}

    try:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM stocks"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug='acoes'"
        ).fetchone()

        return {
            "status":       "ok",
            "path":         str(path),
            "db_size_kb":   round(path.stat().st_size / 1024, 1),
            "total_rows":   total_rows,
            "last_date":    sync_row["last_date"] if sync_row else "",
            "last_sync":    sync_row["synced_at"] if sync_row else "",
            "synced_rows":  sync_row["row_count"] if sync_row else 0,
        }
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()
