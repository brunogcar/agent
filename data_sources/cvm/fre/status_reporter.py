"""data_sources/cvm/fre/status_reporter.py -- FRE database status."""

from __future__ import annotations

from data_sources.cvm._db import connect_fre, fre_db_path


def status() -> dict:
    """Return FRE database statistics."""
    path = fre_db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "FRE database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect_fre(read_only=True)
    try:
        doc_count = conn.execute("SELECT COUNT(*) as n FROM documentos").fetchone()["n"]
        pos_count = conn.execute("SELECT COUNT(*) as n FROM posicao_acionaria").fetchone()["n"]
        dist_count = conn.execute("SELECT COUNT(*) as n FROM distribuicao_capital").fetchone()["n"]
        rem_count = conn.execute("SELECT COUNT(*) as n FROM remuneracao_orgao").fetchone()["n"]
        cap_count = conn.execute("SELECT COUNT(*) as n FROM capital_social").fetchone()["n"]

        year_row = conn.execute(
            "SELECT MIN(ano_origem) as min_year, MAX(ano_origem) as max_year FROM documentos"
        ).fetchone()

        synced = conn.execute(
            "SELECT * FROM sync_state ORDER BY year"
        ).fetchall()

        return {
            "status": "ok",
            "form": "FRE",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "tables": {
                "documentos": doc_count,
                "posicao_acionaria": pos_count,
                "distribuicao_capital": dist_count,
                "remuneracao_orgao": rem_count,
                "capital_social": cap_count,
            },
            "year_range": {
                "min": year_row["min_year"] if year_row else None,
                "max": year_row["max_year"] if year_row else None,
            },
            "synced_years": [{
                "year": r["year"],
                "synced_at": r["synced_at"],
                "rows_documentos": r["rows_documentos"],
                "rows_posicao": r["rows_posicao"],
                "rows_distrib": r["rows_distrib"],
                "rows_remuneracao": r["rows_remuneracao"],
                "rows_capital": r["rows_capital"],
            } for r in synced],
        }

    except sqlite3.OperationalError:
        return {
            "status": "not_synced",
            "message": "FRE database exists but tables not created. Run sync first.",
            "path": str(path),
        }
    finally:
        conn.close()
