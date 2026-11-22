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

        # [v2] Evolution store stats — stocks_history (one row per ticker
        # per sync day). history_dates counts the DISTINCT snapshot dates
        # (the series length behind the distribution-over-time charts).
        try:
            hist_row = conn.execute(
                "SELECT COUNT(*) as rows_n, "
                "COUNT(DISTINCT ref_date) as dates_n FROM stocks_history"
            ).fetchone()
            history_rows = hist_row["rows_n"]
            history_dates = hist_row["dates_n"]
        except Exception:
            # Pre-v2 DB without the table yet (created on next sync).
            history_rows = 0
            history_dates = 0

        return {
            "status":         "ok",
            "path":           str(path),
            "db_size_kb":     db_size_kb,
            "total_rows":     total_rows,
            "last_date":      sync_row["last_date"] if sync_row else "",
            "last_sync":      sync_row["synced_at"] if sync_row else "",
            "synced_rows":    sync_row["row_count"] if sync_row else 0,
            "history_rows":   history_rows,
            "history_dates":  history_dates,
        }


def status() -> dict:
    """Show acoes.db stats: row count + last sync timestamp."""
    return _StatusReporter.status(db_path, connect)
