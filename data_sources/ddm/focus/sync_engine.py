"""data_sources/ddm/focus/sync_engine.py -- Sync DDM focus data to SQLite.

Two sync entry points:
  1. sync_all(force=False)            - fetch + parse + store the focus page
                                        (single HTTP call, single page)
  2. sync_index(slug="focus", force)  - alias for sync_all (parity with the
                                        other DDM sub-domains; the focus page
                                        is single-page, not per-index)

Idempotency: uses INSERT OR REPLACE on the (year, indicator, ref_date)
primary key. Re-syncing the same day replaces existing rows for that
ref_date rather than appending duplicates. Different ref_dates accumulate
into a historical snapshot series (Focus is weekly, so consecutive syncs
on different days yield different ref_dates and the history grows).

[Phase 3, Commit 1] Refactored to delegate to `data_sources/ddm/_base/`
(BaseDDMSyncEngine.sync_single_page). The fetch + parse + INSERT +
sync_state pattern now lives in _base/sync_base.py; this module keeps
only the per-source config (fetcher fn, parser fn, INSERT SQL, row
mapper, last_date computation, result extras) + the sync_index() alias.

B4 stale-row cleanup is NOT enabled for focus (full_refresh=False): focus
keyed by (year, indicator, ref_date) where ref_date is the sync date, so
historical snapshots accumulate by design (different ref_dates form a
time series). DELETE-then-INSERT would wipe the history.
"""

from __future__ import annotations

from data_sources.ddm._base.sync_base import BaseDDMSyncEngine
from data_sources.ddm.focus.catalog import (
    connect, ensure_schema,
)
from data_sources.ddm.focus.fetcher import fetch_focus_page, parse_focus_tables

class _SyncEngine(BaseDDMSyncEngine):
    """Focus-specific sync engine config (SOURCE_NAME for log prefix)."""

    SOURCE_NAME = "focus"

_INSERT_SQL = (
    "INSERT OR REPLACE INTO focus_observations "
    "(year, indicator, four_weeks_ago, one_week_ago, today, "
    " comparison, respondents, ref_date, synced_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

def _row_mapper(obs: dict, now: str) -> tuple:
    """ref_date = today's date (focus does not expose a publication date).

    Focus is weekly; DDM does not expose a publication-date column on the
    page itself, so the sync date is the closest proxy for the bulletin's
    reference week.
    """
    ref_date = _SyncEngine._today_date()
    return (
        obs["year"], obs["indicator"], obs.get("four_weeks_ago"),
        obs.get("one_week_ago"), obs.get("today"), obs.get("comparison"),
        obs.get("respondents"), ref_date, now,
    )

def _compute_last_date(observations: list[dict]) -> str:
    """last_date = today's date (the ref_date of THIS sync)."""
    return _SyncEngine._today_date()

def _result_extras(observations: list[dict], last_date: str, now: str) -> dict:
    """Extra keys to merge into the sync_all() result dict.

    focus returns `ref_date` (= today's date) alongside `rows` + `synced_at`
    so callers can show the bulletin's reference week in the dashboard.
    """
    return {"ref_date": last_date}

def sync_all(force: bool = False) -> dict:
    """Sync the /boletim-focus page into focus.db.

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "rows": <int>, "ref_date": <str>,
         "synced_at": <iso>}

    The sync is a single HTTP call (no ThreadPoolExecutor needed - the
    focus page is one document, not per-index). All parsed observations
    for the current ref_date are INSERTed OR REPLACEd into focus.db,
    keyed by (year, indicator, ref_date). Earlier ref_dates are preserved
    so consumers can query the history of focus expectations over time.

    B4 stale-row cleanup is NOT enabled: focus accumulates history by
    ref_date (weekly snapshots), so DELETE-then-INSERT would wipe the
    time series.
    """
    return _SyncEngine.sync_single_page(
        fetch_fn=fetch_focus_page,
        parse_fn=parse_focus_tables,
        connect_fn=connect,
        ensure_schema_fn=ensure_schema,
        insert_sql=_INSERT_SQL,
        row_mapper=_row_mapper,
        slug="focus",
        # focus accumulates history by ref_date -- no B4 cleanup.
        full_refresh=False,
        compute_last_date=_compute_last_date,
        result_extras=_result_extras,
        force=force,
    )

