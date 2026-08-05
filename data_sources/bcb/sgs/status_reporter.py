"""data_sources/bcb/sgs/status_reporter.py -- sgs.db sync statistics.

Mirrors the brapi status_reporter pattern: a single status() function that
returns DB path, size, per-series row counts, and last-sync timestamps.

[v3] Reads sync_state using the v1 schema (series_code / last_date /
synced_at / row_count) instead of v2's generic (key / value / synced_at).
"""

from __future__ import annotations

from data_sources.bcb.sgs.catalog import connect, db_path, SERIES_CATALOG


def status() -> dict:
    """Show sgs.db stats: per-series row counts + last sync timestamps."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "sgs.db not found. Run sync_all first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "sgs.db not found."}

    try:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM series_observations"
        ).fetchone()["n"]

        per_series = []
        for code, meta in sorted(SERIES_CATALOG.items()):
            row = conn.execute(
                "SELECT COUNT(*) as n, MAX(ref_date) as last_date "
                "FROM series_observations WHERE series_code=?",
                (code,),
            ).fetchone()
            # [v3] sync_state uses series_code as TEXT primary key.
            sync_row = conn.execute(
                "SELECT last_date, synced_at, row_count FROM sync_state "
                "WHERE series_code=?",
                (str(code),),
            ).fetchone()
            per_series.append({
                "code": code,
                "name": meta[0],
                "frequency": meta[1],
                "unit": meta[2],
                "category": meta[3],
                "rows": row["n"] if row else 0,
                "last_ref_date": row["last_date"] if row else "",
                "last_sync": sync_row["synced_at"] if sync_row else "",
                "synced_rows": sync_row["row_count"] if sync_row else 0,
            })

        return {
            "status": "ok",
            "path": str(path),
            "db_size_kb": round(path.stat().st_size / 1024, 1),
            "series_count": len(SERIES_CATALOG),
            "total_rows": total_rows,
            "series": per_series,
        }
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()
