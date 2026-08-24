"""data_sources/ddm/fluxo/sync_engine.py -- Sync DDM fluxo data to SQLite.

Two sync entry points:
  1. sync_all(force=False)            - fetch + parse + store the fluxo page
                                        (single HTTP call, single page)
  2. sync_index(slug="fluxo", force)  - alias for sync_all (parity with the
                                        other DDM sub-domains; the fluxo page
                                        is single-page, not per-index)

Idempotency: uses INSERT OR REPLACE on the ref_date primary key. Re-syncing
the same day replaces existing rows rather than appending duplicates. New
days (new trading days) accumulate into the historical series.

[Phase 3, Commit 1] Refactored to delegate to `data_sources/ddm/_base/`
(BaseDDMSyncEngine.sync_single_page). The fetch + parse + DELETE + INSERT
+ sync_state pattern now lives in _base/sync_base.py; this module keeps
only the per-source config (fetcher fn, parser fn, INSERT SQL, row
mapper, B4 full-refresh flag, last_date computation, result extras) +
the sync_index() alias.

NEW in Phase 3, Commit 1: B4 stale-row cleanup is now enabled for fluxo
(full_refresh=True, table_name="fluxo_observations"). The /fluxo page is
a daily full-refresh snapshot (~247 trading days republished daily), so
DELETE-then-INSERT is safe and prevents stale trading-day rows from
lingering when DDM drops them from the page. This matches the existing
pattern in ddm/acoes + ddm/dividends.

B4 is NOT enabled for inflation/juros/poupanca (keyed by (slug, ref_date)
where ref_date is the data's month -- monthly history accumulates) or for
focus (keyed by (year, indicator, ref_date) where ref_date is the sync
date -- weekly snapshots accumulate by design).
"""

from __future__ import annotations

from data_sources.ddm._base.sync_base import BaseDDMSyncEngine
from data_sources.ddm.fluxo.catalog import (
    connect, ensure_schema,
)
from data_sources.ddm.fluxo.fetcher import fetch_fluxo_page, parse_fluxo_table

class _SyncEngine(BaseDDMSyncEngine):
    """Fluxo-specific sync engine config (SOURCE_NAME for log prefix)."""

    SOURCE_NAME = "fluxo"

_INSERT_SQL = (
    "INSERT OR REPLACE INTO fluxo_observations "
    "(ref_date, estrangeiro, institucional, pessoa_fisica, "
    " inst_financeira, outros, synced_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

def _row_mapper(obs: dict, now: str) -> tuple:
    return (
        obs["ref_date"], obs.get("estrangeiro"), obs.get("institucional"),
        obs.get("pessoa_fisica"), obs.get("inst_financeira"),
        obs.get("outros"), now,
    )

def _compute_last_date(observations: list[dict]) -> str:
    """last_date = the most recent ref_date in the synced observations.

    The /fluxo page is DESC (newest first), so the first observation is
    the most recent trading day. We compute max() defensively in case
    the source order changes.
    """
    if not observations:
        return ""
    return max(
        (o["ref_date"] for o in observations if o.get("ref_date")),
        default="",
    )

def _result_extras(observations: list[dict], last_date: str, now: str) -> dict:
    """Extra keys to merge into the sync_all() result dict.

    fluxo returns `last_date` alongside `rows` + `synced_at` so callers
    can show the most recent trading day in the dashboard without an
    extra DB query.
    """
    return {"last_date": last_date}

def sync_all(force: bool = False) -> dict:
    """Sync the /fluxo page into fluxo.db.

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "rows": <int>, "last_date": <str>,
         "synced_at": <iso>}

    The sync is a single HTTP call (no ThreadPoolExecutor needed - the
    fluxo page is one document, not per-index). All parsed observations
    are INSERTed OR REPLACEd into fluxo.db, keyed by ref_date.

    [Phase 3, Commit 1] B4 stale-row cleanup is now ENABLED: existing
    fluxo_observations rows are DELETEd before the new INSERT batch.
    This removes stale trading-day rows when DDM drops them from the
    page (full-refresh pattern, same as acoes + dividends).
    """
    return _SyncEngine.sync_single_page(
        fetch_fn=fetch_fluxo_page,
        parse_fn=parse_fluxo_table,
        connect_fn=connect,
        ensure_schema_fn=ensure_schema,
        insert_sql=_INSERT_SQL,
        row_mapper=_row_mapper,
        slug="fluxo",
        table_name="fluxo_observations",
        # [Phase 3, Commit 1] NEW: B4 stale-row cleanup for fluxo.
        # The /fluxo page is a daily full-refresh snapshot, so
        # DELETE-then-INSERT is safe and prevents stale trading-day rows.
        full_refresh=True,
        compute_last_date=_compute_last_date,
        result_extras=_result_extras,
        force=force,
    )

