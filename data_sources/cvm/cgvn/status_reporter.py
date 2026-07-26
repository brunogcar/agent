"""data_sources/cvm/cgvn/status_reporter.py -- CGVN sync statistics."""

from __future__ import annotations

from pathlib import Path


def status() -> dict:
    """Return CGVN database statistics."""
    from data_sources.cvm._db import connect_cgvn, cgvn_db_path
    path = cgvn_db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "CGVN database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect_cgvn(read_only=True)
    try:
        doc_count = conn.execute("SELECT COUNT(*) as n FROM cgvn_documents").fetchone()["n"]
        prac_count = conn.execute("SELECT COUNT(*) as n FROM cgvn_practices").fetchone()["n"]

        date_range = conn.execute(
            "SELECT MIN(Data_Referencia) as min_date, MAX(Data_Referencia) as max_date "
            "FROM cgvn_practices WHERE Data_Referencia IS NOT NULL"
        ).fetchone()

        company_count = conn.execute(
            "SELECT COUNT(DISTINCT CNPJ_Companhia) as n FROM cgvn_practices"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT * FROM sync_state ORDER BY rowid DESC LIMIT 1"
        ).fetchone()

        return {
            "status": "ok",
            "form": "CGVN",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "document_count": doc_count,
            "practice_count": prac_count,
            "company_count": company_count,
            "earliest_date": date_range["min_date"] if date_range else "",
            "latest_date": date_range["max_date"] if date_range else "",
            "synced_at": sync_row["synced_at"] if sync_row else "",
            "last_sync_year": sync_row["year"] if sync_row else 0,
        }
    finally:
        conn.close()
