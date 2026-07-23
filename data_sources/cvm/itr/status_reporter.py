"""data_sources/cvm/itr/status_reporter.py -- ITR database status."""

from __future__ import annotations

from data_sources.cvm._db import connect_itr, itr_db_path


def status() -> dict:
    """Return ITR database statistics."""
    path = itr_db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "ITR database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect_itr(read_only=True)
    try:
        emp_count = conn.execute("SELECT COUNT(*) as n FROM empresas").fetchone()["n"]
        conta_count = conn.execute("SELECT COUNT(*) as n FROM contas").fetchone()["n"]

        year_row = conn.execute(
            "SELECT MIN(ano) as min_year, MAX(ano) as max_year FROM empresas"
        ).fetchone()

        synced = conn.execute(
            "SELECT year, synced_at, row_count FROM sync_state WHERE form='ITR' ORDER BY year"
        ).fetchall()

        grupos = conn.execute(
            "SELECT grupo, COUNT(*) as n FROM contas GROUP BY grupo ORDER BY n DESC"
        ).fetchall()

        meses_dist = conn.execute(
            "SELECT meses, COUNT(*) as n FROM contas GROUP BY meses ORDER BY meses"
        ).fetchall()

        return {
            "status": "ok",
            "form": "ITR",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "empresas": emp_count,
            "contas": conta_count,
            "year_range": {
                "min": year_row["min_year"] if year_row else None,
                "max": year_row["max_year"] if year_row else None,
            },
            "synced_years": [{
                "year": r["year"],
                "synced_at": r["synced_at"],
                "rows": r["row_count"],
            } for r in synced],
            "grupos": {r["grupo"]: r["n"] for r in grupos},
            "meses_distribution": {r["meses"]: r["n"] for r in meses_dist},
        }

    finally:
        conn.close()
