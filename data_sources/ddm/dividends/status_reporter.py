"""data_sources/ddm/dividends/status_reporter.py -- dividends.db sync statistics.

Mirrors the bcb/sgs + ddm/inflation/juros/poupanca status_reporter pattern:
a single status() function that returns DB path, size, total rows, by-tipo
counts, and last sync timestamp.
"""

from __future__ import annotations

from data_sources.ddm.dividends.catalog import connect, db_path


def status() -> dict:
    """Show dividends.db stats: total rows + per-tipo counts + last sync."""
    path = db_path()
    if not path.exists():
        return {"status": "not_synced",
                "message": "dividends.db not found. Run sync_all first."}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "dividends.db not found."}

    try:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM dividends"
        ).fetchone()["n"]

        by_tipo: dict[str, int] = {}
        for r in conn.execute(
            "SELECT tipo, COUNT(*) as n FROM dividends GROUP BY tipo"
        ).fetchall():
            by_tipo[r["tipo"] or "?"] = r["n"]

        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug=?",
            ("dividends",),
        ).fetchone()

        return {
            "status":      "ok",
            "path":        str(path),
            "db_size_kb":  round(path.stat().st_size / 1024, 1),
            "total_rows":  total_rows,
            "by_tipo":     by_tipo,
            "last_date":   sync_row["last_date"] if sync_row else "",
            "last_sync":   sync_row["synced_at"] if sync_row else "",
            "synced_rows": sync_row["row_count"] if sync_row else 0,
        }
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()
