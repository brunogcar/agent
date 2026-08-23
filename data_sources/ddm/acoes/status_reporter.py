"""data_sources/ddm/acoes/status_reporter.py -- acoes.db sync statistics.

Mirrors the ddm/inflation + ddm/juros + ddm/poupanca status_reporter pattern:
a single status() function that returns DB path, size, row count, and
last-sync timestamp.

[Phase 3, Commit 1] Refactored to inherit from
`data_sources/ddm/_base/status_base.py` (BaseDDMStatusReporter). The shared
path-check + connect + try/except + finally scaffold now lives in
_base/status_base.py; this module keeps only the source-specific
queries (single SELECT COUNT(*) FROM stocks + sync_state lookup).
"""

from __future__ import annotations

from data_sources.ddm._base.status_base import BaseDDMStatusReporter
from data_sources.ddm.acoes.catalog import (
    connect, db_path,
)


class _StatusReporter(BaseDDMStatusReporter):
    """Acoes-specific status reporter (SOURCE_NAME for not_synced msg)."""

    SOURCE_NAME = "acoes"

    @classmethod
    def _build_status_dict(cls, conn, path, db_size_kb: float) -> dict:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM stocks"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug='acoes'"
        ).fetchone()

        return {
            "status":       "ok",
            "path":         str(path),
            "db_size_kb":   db_size_kb,
            "total_rows":   total_rows,
            "last_date":    sync_row["last_date"] if sync_row else "",
            "last_sync":    sync_row["synced_at"] if sync_row else "",
            "synced_rows":  sync_row["row_count"] if sync_row else 0,
        }


def status() -> dict:
    """Show acoes.db stats: row count + last sync timestamp."""
    return _StatusReporter.status(db_path, connect)
