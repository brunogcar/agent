"""data_sources/ddm/fluxo/status_reporter.py -- fluxo.db sync statistics.

Mirrors the ddm/focus status_reporter pattern: a single status() function
that returns DB path, size, row count, date range, and last-sync timestamp.

[Phase 3, Commit 1] Refactored to inherit from
`data_sources/ddm/_base/status_base.py` (BaseDDMStatusReporter). The shared
path-check + connect + try/except + finally scaffold now lives in
_base/status_base.py; this module keeps only the source-specific
queries (COUNT(*) + sync_state + MIN/MAX(ref_date)).
"""

from __future__ import annotations

from data_sources.ddm._base.status_base import BaseDDMStatusReporter
from data_sources.ddm.fluxo.catalog import (
    connect, db_path,
)


class _StatusReporter(BaseDDMStatusReporter):
    """Fluxo-specific status reporter (SOURCE_NAME for not_synced msg)."""

    SOURCE_NAME = "fluxo"

    @classmethod
    def _build_status_dict(cls, conn, path, db_size_kb: float) -> dict:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM fluxo_observations"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug='fluxo'"
        ).fetchone()

        range_row = conn.execute(
            "SELECT MIN(ref_date) as first_date, MAX(ref_date) as last_date "
            "FROM fluxo_observations"
        ).fetchone()

        return {
            "status":       "ok",
            "path":         str(path),
            "db_size_kb":   db_size_kb,
            "total_rows":   total_rows,
            "first_date":   range_row["first_date"] if range_row else "",
            "last_date":    (sync_row["last_date"] if sync_row else
                             (range_row["last_date"] if range_row else "")),
            "last_sync":    sync_row["synced_at"] if sync_row else "",
            "synced_rows":  sync_row["row_count"] if sync_row else 0,
        }


def status() -> dict:
    """Show fluxo.db stats: row count + date range + last sync."""
    return _StatusReporter.status(db_path, connect)
