"""data_sources/bcb/focus/status_reporter.py -- focus.db sync statistics.

Mirrors the sgs status_reporter pattern: a single status() function that
returns DB path, size, per-indicator row counts, and last-sync timestamps.
"""

from __future__ import annotations

from data_sources.bcb.focus.catalog import (
    connect, db_path, INDICATOR_CATALOG, DEFAULT_INDICATORS,
)


def _table_for_frequency(frequency: str) -> str:
    if frequency == "monthly":
        return "expectations_monthly"
    if frequency == "annual":
        return "expectations_annual"
    raise ValueError(f"Unknown frequency: {frequency!r}")


def status() -> dict:
    """Show focus.db stats: per-indicator row counts + last sync timestamps."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "focus.db not found. Run sync_all first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "focus.db not found."}

    try:
        # Total row count across both tables.
        monthly_rows = conn.execute(
            "SELECT COUNT(*) as n FROM expectations_monthly"
        ).fetchone()
        annual_rows = conn.execute(
            "SELECT COUNT(*) as n FROM expectations_annual"
        ).fetchone()
        total_rows = ((monthly_rows["n"] if monthly_rows else 0) +
                      (annual_rows["n"] if annual_rows else 0))

        per_indicator = []
        for indicador, frequency in DEFAULT_INDICATORS:
            meta = INDICATOR_CATALOG.get(indicador, (indicador, "", "", ""))
            table = _table_for_frequency(frequency)
            row = conn.execute(
                f"SELECT COUNT(*) as n, MAX(data) as last_data "
                f"FROM {table} WHERE indicador = ?",
                (indicador,),
            ).fetchone()
            sync_row = conn.execute(
                "SELECT last_date, synced_at, row_count FROM sync_state "
                "WHERE indicador = ?",
                (indicador,),
            ).fetchone()
            per_indicator.append({
                "indicador": indicador,
                "frequency": frequency,
                "description": meta[2],
                "unit": meta[3],
                "rows": row["n"] if row else 0,
                "last_data": row["last_data"] if row else "",
                "last_sync": sync_row["synced_at"] if sync_row else "",
                "synced_rows": sync_row["row_count"] if sync_row else 0,
            })

        return {
            "status": "ok",
            "path": str(path),
            "db_size_kb": round(path.stat().st_size / 1024, 1),
            "indicator_count": len(DEFAULT_INDICATORS),
            "total_rows": total_rows,
            "monthly_rows": monthly_rows["n"] if monthly_rows else 0,
            "annual_rows": annual_rows["n"] if annual_rows else 0,
            "indicators": per_indicator,
        }
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()
