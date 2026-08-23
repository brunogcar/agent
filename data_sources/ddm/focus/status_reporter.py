"""data_sources/ddm/focus/status_reporter.py -- focus.db sync statistics.

Mirrors the ddm/acoes status_reporter pattern: a single status() function
that returns DB path, size, row count, distinct year/indicator counts, and
last-sync timestamp.

[Phase 3, Commit 1] Refactored to inherit from
`data_sources/ddm/_base/status_base.py` (BaseDDMStatusReporter). The shared
path-check + connect + try/except + finally scaffold now lives in
_base/status_base.py; this module keeps only the source-specific
queries (COUNT(*) + sync_state + DISTINCT year + DISTINCT indicator).
"""

from __future__ import annotations

from data_sources.ddm._base.status_base import BaseDDMStatusReporter
from data_sources.ddm.focus.catalog import (
    connect, db_path,
)


class _StatusReporter(BaseDDMStatusReporter):
    """Focus-specific status reporter (SOURCE_NAME for not_synced msg)."""

    SOURCE_NAME = "focus"

    @classmethod
    def _build_status_dict(cls, conn, path, db_size_kb: float) -> dict:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM focus_observations"
        ).fetchone()["n"]

        sync_row = conn.execute(
            "SELECT last_date, synced_at, row_count FROM sync_state "
            "WHERE slug='focus'"
        ).fetchone()

        year_rows = conn.execute(
            "SELECT DISTINCT year FROM focus_observations ORDER BY year ASC"
        ).fetchall()
        ind_rows = conn.execute(
            "SELECT DISTINCT indicator FROM focus_observations "
            "ORDER BY indicator ASC"
        ).fetchall()

        return {
            "status":           "ok",
            "path":             str(path),
            "db_size_kb":       db_size_kb,
            "total_rows":       total_rows,
            "year_count":       len(year_rows),
            "indicator_count":  len(ind_rows),
            "years":            [r["year"] for r in year_rows],
            "indicators":       [r["indicator"] for r in ind_rows],
            "last_date":        sync_row["last_date"] if sync_row else "",
            "last_sync":        sync_row["synced_at"] if sync_row else "",
            "synced_rows":      sync_row["row_count"] if sync_row else 0,
        }


def status() -> dict:
    """Show focus.db stats: row count + year/indicator counts + last sync."""
    return _StatusReporter.status(db_path, connect)
