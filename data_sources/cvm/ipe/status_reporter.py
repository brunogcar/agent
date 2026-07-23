"""data_sources/cvm/ipe/status_reporter.py -- IPE database status."""

from __future__ import annotations

import sqlite3

from data_sources.cvm._db import connect_ipe, ipe_db_path


def status() -> dict:
    """Return IPE database statistics."""
    path = ipe_db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "IPE database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect_ipe(read_only=True)
    try:
        event_count = conn.execute("SELECT COUNT(*) as n FROM eventos").fetchone()["n"]

        year_row = conn.execute(
            "SELECT MIN(ano_origem) as min_year, MAX(ano_origem) as max_year FROM eventos"
        ).fetchone()

        synced = conn.execute(
            "SELECT * FROM sync_state ORDER BY year"
        ).fetchall()

        # Category breakdown
        categorias = conn.execute(
            "SELECT categoria, COUNT(*) as n FROM eventos GROUP BY categoria ORDER BY n DESC LIMIT 10"
        ).fetchall()

        return {
            "status": "ok",
            "form": "IPE",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "eventos": event_count,
            "year_range": {
                "min": year_row["min_year"] if year_row else None,
                "max": year_row["max_year"] if year_row else None,
            },
            "synced_years": [{
                "year": r["year"],
                "synced_at": r["synced_at"],
                "rows_added": r["rows_added"],
            } for r in synced],
            "top_categorias": {r["categoria"]: r["n"] for r in categorias},
        }

    except sqlite3.OperationalError:
        return {
            "status": "not_synced",
            "message": "IPE database exists but tables not created. Run sync first.",
            "path": str(path),
        }
    finally:
        conn.close()
