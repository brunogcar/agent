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

[v2] Added schema migration: if the DB has the old TEXT schema (v1),
automatically migrates to REAL by casting existing data. SQLite doesn't
support ALTER COLUMN, so we use CREATE-new + INSERT-with-cast + DROP +
RENAME. Runs once on first sync after upgrade.
[I12] Added incremental sync: if today's data already exists in the DB
(ref_date == today), skip the fetch entirely (unless force=True).

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

import sqlite3

from data_sources.ddm._base.sync_base import BaseDDMSyncEngine
from data_sources.ddm.focus.catalog import (
    MIGRATION_SQL, connect, ensure_schema,
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

    [v2] Values are now float (parsed at fetch time), not PT-BR strings.
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


def _needs_migration(conn) -> bool:
    """Check if the DB has the old TEXT schema (v1) that needs migration.

    Returns True if any of the value columns (four_weeks_ago, one_week_ago,
    today) are TEXT instead of REAL.
    """
    try:
        cols = conn.execute("PRAGMA table_info(focus_observations)").fetchall()
        for col in cols:
            if col["name"] in ("four_weeks_ago", "one_week_ago", "today"):
                if str(col["type"]).upper() == "TEXT":
                    return True
        return False
    except sqlite3.Error:
        return False


def _run_migration(conn) -> None:
    """Run the TEXT → REAL migration (C2 fix).

    Uses the CREATE-new + INSERT-with-cast + DROP + RENAME pattern because
    SQLite doesn't support ALTER COLUMN. Preserves all existing data by
    casting TEXT values to REAL.
    """
    _SyncEngine._progress("[ddm.focus] Migrating schema: TEXT → REAL")
    conn.executescript(MIGRATION_SQL)
    conn.commit()
    _SyncEngine._progress("[ddm.focus] Migration complete")


def _today_data_exists() -> bool:
    """Check if today's data already exists in the DB (I12 incremental sync).

    Returns True if there are any rows with ref_date == today's date.
    """
    today = _SyncEngine._today_date()
    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return False
    try:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM focus_observations WHERE ref_date=?",
            (today,),
        ).fetchone()
        return row["n"] > 0 if row else False
    except sqlite3.Error:
        return False
    finally:
        conn.close()


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

    [v2] Runs schema migration (TEXT → REAL) if needed.
    [I12] Skips fetch if today's data already exists (unless force=True).
    """
    # [I12] Incremental sync: skip if today's data already exists.
    if not force and _today_data_exists():
        _SyncEngine._progress(
            f"[ddm.focus] Today's data already synced (ref_date={_SyncEngine._today_date()}) — skipping fetch"
        )
        return {
            "status": "ok",
            "rows": 0,
            "ref_date": _SyncEngine._today_date(),
            "synced_at": _SyncEngine._now(),
            "skipped": True,
        }

    # [v2] Run schema migration if needed (TEXT → REAL).
    try:
        conn = connect(read_only=False)
        ensure_schema(conn)
        if _needs_migration(conn):
            _run_migration(conn)
        conn.close()
    except Exception as e:
        _SyncEngine._progress(f"[ddm.focus] Migration check failed: {e}")

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
