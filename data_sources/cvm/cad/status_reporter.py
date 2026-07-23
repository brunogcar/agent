"""data_sources/cvm/cad/status_reporter.py -- CAD database status."""

from __future__ import annotations

import sqlite3

from data_sources.cvm._db import connect_cad, cad_db_path


def status() -> dict:
    """Return CAD database statistics."""
    path = cad_db_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "CAD database not found. Run sync first.",
            "path": str(path),
        }

    conn = connect_cad(read_only=True)
    try:
        total = conn.execute("SELECT COUNT(*) as n FROM cia_aberta").fetchone()["n"]
        active = conn.execute("SELECT COUNT(*) as n FROM cia_aberta WHERE SIT='ATIVO'").fetchone()["n"]
        cancelled = conn.execute("SELECT COUNT(*) as n FROM cia_aberta WHERE SIT='CANCELADA'").fetchone()["n"]

        sync_row = conn.execute(
            "SELECT * FROM sync_state ORDER BY synced_at DESC LIMIT 1"
        ).fetchone()

        # Sector breakdown (top 10)
        sectors = conn.execute(
            "SELECT SETOR_ATIV, COUNT(*) as n FROM cia_aberta "
            "WHERE SIT='ATIVO' AND SETOR_ATIV != '' "
            "GROUP BY SETOR_ATIV ORDER BY n DESC LIMIT 10"
        ).fetchall()

        # Market type breakdown
        mercados = conn.execute(
            "SELECT TP_MERC, COUNT(*) as n FROM cia_aberta "
            "WHERE SIT='ATIVO' AND TP_MERC != '' "
            "GROUP BY TP_MERC ORDER BY n DESC"
        ).fetchall()

        return {
            "status": "ok",
            "form": "CAD",
            "path": str(path),
            "db_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "total_companies": total,
            "active": active,
            "cancelled": cancelled,
            "last_sync": {
                "synced_at": sync_row["synced_at"] if sync_row else "",
                "rows": sync_row["rows"] if sync_row else 0,
                "size_kb": sync_row["size_kb"] if sync_row else 0,
            },
            "top_sectors": {r["SETOR_ATIV"]: r["n"] for r in sectors},
            "market_types": {r["TP_MERC"]: r["n"] for r in mercados},
        }

    except sqlite3.OperationalError:
        return {
            "status": "not_synced",
            "message": "CAD database exists but tables not created. Run sync first.",
            "path": str(path),
        }
    finally:
        conn.close()
