"""data_sources/ddm/poupanca/status_reporter.py -- poupanca.db sync statistics.

Mirrors the bcb/sgs + ddm/inflation + ddm/juros status_reporter pattern: a
single status() function that returns DB path, size, per-index row counts,
and last-sync timestamps.

[Phase 3, Commit 1] Refactored to inherit from
`data_sources/ddm/_base/status_base.py` (BaseDDMStatusReporter). The shared
path-check + connect + try/except + finally scaffold now lives in
_base/status_base.py; this module keeps only the source-specific
queries (per-index loop over POUPANCA_CATALOG).
"""

from __future__ import annotations

from data_sources.ddm._base.status_base import BaseDDMStatusReporter
from data_sources.ddm.poupanca.catalog import (
    POUPANCA_CATALOG, connect, db_path,
)


class _StatusReporter(BaseDDMStatusReporter):
    """Poupanca-specific status reporter (SOURCE_NAME for not_synced msg)."""

    SOURCE_NAME = "poupanca"

    @classmethod
    def _build_status_dict(cls, conn, path, db_size_kb: float) -> dict:
        total_rows = conn.execute(
            "SELECT COUNT(*) as n FROM poupanca_observations"
        ).fetchone()["n"]

        per_index = []
        for slug, meta in sorted(POUPANCA_CATALOG.items()):
            row = conn.execute(
                "SELECT COUNT(*) as n, MAX(ref_date) as last_date "
                "FROM poupanca_observations WHERE slug=?",
                (slug,),
            ).fetchone()
            sync_row = conn.execute(
                "SELECT last_date, synced_at, row_count FROM sync_state "
                "WHERE slug=?",
                (slug,),
            ).fetchone()
            per_index.append({
                "slug":          slug,
                "name":          meta[0],
                "category":      meta[1],
                "unit":          meta[3],
                "rows":          row["n"] if row else 0,
                "last_ref_date": row["last_date"] if row else "",
                "last_sync":     sync_row["synced_at"] if sync_row else "",
                "synced_rows":   sync_row["row_count"] if sync_row else 0,
            })

        return {
            "status":        "ok",
            "path":          str(path),
            "db_size_kb":    db_size_kb,
            "indices_count": len(POUPANCA_CATALOG),
            "total_rows":    total_rows,
            "indices":       per_index,
        }


def status() -> dict:
    """Show poupanca.db stats: per-index row counts + last sync timestamps."""
    return _StatusReporter.status(db_path, connect)
