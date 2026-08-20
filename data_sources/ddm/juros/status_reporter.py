"""data_sources/ddm/juros/status_reporter.py -- juros.db sync statistics.

Mirrors the bcb/sgs + ddm/inflation status_reporter pattern: a single
status() function that returns DB path, size, per-index row counts, and
last-sync timestamps.
"""

from __future__ import annotations

from data_sources.ddm.juros.catalog import (
    JUROS_CATALOG, connect, db_path,
)


def status() -> dict:
    """Show juros.db stats: per-index row counts + last sync timestamps."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "juros.db not found. Run sync_all first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "juros.db not found."}

    try:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM juros_observations"
        ).fetchone()["n"]

        per_index = []
        for slug, meta in sorted(JUROS_CATALOG.items()):
            row = conn.execute(
                "SELECT COUNT(*) as n, MAX(ref_date) as last_date "
                "FROM juros_observations WHERE slug=?",
                (slug,),
            ).fetchone()
            sync_row = conn.execute(
                "SELECT last_date, synced_at, row_count FROM sync_state "
                "WHERE slug=?",
                (slug,),
            ).fetchone()
            per_index.append({
                "slug":          slug,
                "name":          meta[0],
                "category":      meta[1],
                "unit":          meta[3],
                "rows":          row["n"] if row else 0,
                "last_ref_date": row["last_date"] if row else "",
                "last_sync":     sync_row["synced_at"] if sync_row else "",
                "synced_rows":   sync_row["row_count"] if sync_row else 0,
            })

        return {
            "status":       "ok",
            "path":         str(path),
            "db_size_kb":   round(path.stat().st_size / 1024, 1),
            "indices_count": len(JUROS_CATALOG),
            "total_rows":   total_rows,
            "indices":      per_index,
        }
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()
