"""data_sources/b3/api/status_reporter.py -- B3 API sync statistics.

[v1.1] Split from query_engine.py to follow the CVM pattern (status_reporter.py
as a separate file). Same status() function, just in its own module.
"""
from __future__ import annotations

from data_sources.b3.api.catalog import B3_TABLES, connect, db_path


def status() -> dict:
    """Show sync status for all B3 tables."""
    import sqlite3

    results = {"status": "ok", "tables": {}}

    for table_name, table_info in B3_TABLES.items():
        path = db_path(table_name)
        if not path.exists():
            results["tables"][table_name] = {
                "status": "not_synced",
                "path": str(path),
            }
            continue

        try:
            conn = connect(table_name, read_only=True)
            try:
                count = conn.execute(
                    f"SELECT COUNT(*) as n FROM {table_info['table']}"
                ).fetchone()["n"]

                sync_rows = conn.execute(
                    "SELECT * FROM sync_state WHERE table_name=? ORDER BY date DESC LIMIT 1",
                    (table_name,),
                ).fetchone()

                results["tables"][table_name] = {
                    "status": "ok",
                    "rows": count,
                    "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
                    "last_sync": {
                        "date": sync_rows["date"] if sync_rows else "",
                        "synced_at": sync_rows["synced_at"] if sync_rows else "",
                        "row_count": sync_rows["row_count"] if sync_rows else 0,
                    } if sync_rows else None,
                }
            except sqlite3.OperationalError:
                results["tables"][table_name] = {
                    "status": "not_synced",
                    "message": "DB exists but tables not created. Run sync first.",
                }
            finally:
                conn.close()
        except Exception as e:
            results["tables"][table_name] = {"status": "error", "error": str(e)}

    return results
