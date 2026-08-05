"""data_sources/b3/index/status_reporter.py -- B3 index database stats."""
from __future__ import annotations

import os
from data_sources.b3.index.catalog import db_path, connect


def status() -> dict:
    """Get B3 index database status."""
    path = db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "db_path": str(path),
            "message": "Run sync: data_source(domain='b3', sub_domain='index', mode='sync_all')",
        }

    size_kb = round(os.path.getsize(path) / 1024, 1)

    conn = connect(read_only=True)
    try:
        cat_count = conn.execute("SELECT COUNT(*) FROM index_catalog").fetchone()[0]
        active_count = conn.execute("SELECT COUNT(*) FROM index_catalog WHERE active=1").fetchone()[0]
        const_count = conn.execute("SELECT COUNT(*) FROM index_constituents").fetchone()[0]
        sync_count = conn.execute("SELECT COUNT(*) FROM sync_state").fetchone()[0]

        return {
            "status": "ok",
            "db_path": str(path),
            "db_size_kb": size_kb,
            "catalog_count": cat_count,
            "active_indices": active_count,
            "constituent_rows": const_count,
            "synced_indices": sync_count,
        }
    finally:
        conn.close()
