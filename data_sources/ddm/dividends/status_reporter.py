"""data_sources/ddm/dividends/status_reporter.py -- dividends.db sync statistics.

Mirrors the bcb/sgs + ddm/inflation/juros/poupanca status_reporter pattern:
a single status() function that returns DB path, size, total rows, by-tipo
counts, and last sync timestamp.

[Phase 3, Commit 1] Refactored to inherit from
`data_sources/ddm/_base/status_base.py` (BaseDDMStatusReporter). The shared
path-check + connect + try/except + finally scaffold now lives in
_base/status_base.py; this module keeps only the source-specific
queries (SELECT COUNT(*) + GROUP BY tipo + sync_state lookup).
"""

from __future__ import annotations

from data_sources.ddm._base.status_base import BaseDDMStatusReporter
from data_sources.ddm.dividends.catalog import connect, db_path


class _StatusReporter(BaseDDMStatusReporter):
    """Dividends-specific status reporter (SOURCE_NAME for not_synced msg)."""

    SOURCE_NAME = "dividends"

    @classmethod
    def _build_status_dict(cls, conn, path, db_size_kb: float) -> dict:
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
            "db_size_kb":  db_size_kb,
            "total_rows":  total_rows,
            "by_tipo":     by_tipo,
            "last_date":   sync_row["last_date"] if sync_row else "",
            "last_sync":   sync_row["synced_at"] if sync_row else "",
            "synced_rows": sync_row["row_count"] if sync_row else 0,
        }


def status() -> dict:
    """Show dividends.db stats: total rows + per-tipo counts + last sync."""
    return _StatusReporter.status(db_path, connect)
