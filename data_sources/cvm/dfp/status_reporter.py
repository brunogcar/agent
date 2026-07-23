"""data_sources/cvm/dfp/status_reporter.py -- DFP database status."""

from __future__ import annotations

from data_sources.cvm._db import connect_dfp, dfp_db_path


def status() -> dict:
    """Return DFP database statistics.

    Returns: row counts, date range, synced years, DB file size.
    """
    path = dfp_db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "DFP database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect_dfp(read_only=True)
    try:
        # Empresa stats
        emp_count = conn.execute("SELECT COUNT(*) as n FROM empresas").fetchone()["n"]

        # Conta stats
        conta_count = conn.execute("SELECT COUNT(*) as n FROM contas").fetchone()["n"]

        # Year range
        year_row = conn.execute(
            "SELECT MIN(ano) as min_year, MAX(ano) as max_year FROM empresas"
        ).fetchone()
        min_year = year_row["min_year"] if year_row else None
        max_year = year_row["max_year"] if year_row else None

        # Synced years
        synced = conn.execute(
            "SELECT year, synced_at, row_count FROM sync_state WHERE form='DFP' ORDER BY year"
        ).fetchall()

        # Group breakdown
        grupos = conn.execute(
            "SELECT grupo, COUNT(*) as n FROM contas GROUP BY grupo ORDER BY n DESC"
        ).fetchall()

        # meses breakdown
        meses_dist = conn.execute(
            "SELECT meses, COUNT(*) as n FROM contas GROUP BY meses ORDER BY meses"
        ).fetchall()

        return {
            "status": "ok",
            "form": "DFP",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "empresas": emp_count,
            "contas": conta_count,
            "year_range": {"min": min_year, "max": max_year},
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
