"""data_sources/cvm/fca/status_reporter.py -- FCA sync statistics."""

from __future__ import annotations

from pathlib import Path


def status() -> dict:
    """Return FCA database statistics."""
    from data_sources.cvm._db import connect_fca, fca_db_path
    path = fca_db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "FCA database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect_fca(read_only=True)
    try:
        geral_count = conn.execute("SELECT COUNT(*) as n FROM fca_geral").fetchone()["n"]
        vm_count = conn.execute("SELECT COUNT(*) as n FROM fca_valor_mobiliario").fetchone()["n"]
        pe_count = conn.execute("SELECT COUNT(*) as n FROM fca_pais_estrangeiro").fetchone()["n"]

        company_count = conn.execute(
            "SELECT COUNT(DISTINCT REPLACE(REPLACE(REPLACE(CNPJ_Companhia,'.',''),'/',''),'-','')) as n "
            "FROM fca_geral"
        ).fetchone()["n"]

        ticker_count = conn.execute(
            "SELECT COUNT(DISTINCT Codigo_Negociacao) as n FROM fca_valor_mobiliario "
            "WHERE Codigo_Negociacao IS NOT NULL AND Codigo_Negociacao != ''"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT * FROM sync_state ORDER BY rowid DESC LIMIT 1"
        ).fetchone()

        return {
            "status": "ok",
            "form": "FCA",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "geral_count": geral_count,
            "valor_mobiliario_count": vm_count,
            "pais_estrangeiro_count": pe_count,
            "company_count": company_count,
            "ticker_count": ticker_count,
            "synced_at": sync_row["synced_at"] if sync_row else "",
            "last_sync_year": sync_row["year"] if sync_row else 0,
        }
    finally:
        conn.close()
