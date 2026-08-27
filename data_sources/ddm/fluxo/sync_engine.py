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

[I12] Incremental sync: when force=False, only INSERT rows with ref_date >
latest_ref_date in the DB. This avoids re-inserting ~750 existing rows on
every sync. When force=True, falls back to full-refresh (DELETE + re-INSERT
all rows) to handle corrections (DDM may revise historical data).

[Phase 3, Commit 1] Refactored to delegate to `data_sources/ddm/_base/`
(BaseDDMSyncEngine.sync_single_page). The fetch + parse + DELETE + INSERT
+ sync_state pattern now lives in _base/sync_base.py; this module keeps
only the per-source config (fetcher fn, parser fn, INSERT SQL, row
mapper, B4 full-refresh flag, last_date computation, result extras) +
the sync_index() alias.
"""

from __future__ import annotations

import sqlite3

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


def _get_latest_ref_date() -> str:
    """[I12] Get the latest ref_date currently in the DB.

    Returns "" if the DB is empty or doesn't exist.
    """
    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return ""
    try:
        row = conn.execute(
            "SELECT MAX(ref_date) as d FROM fluxo_observations"
        ).fetchone()
        return row["d"] if row and row["d"] else ""
    except sqlite3.Error:
        return ""
    finally:
        conn.close()


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

    [I12] Incremental sync: when force=False, only INSERT rows with
    ref_date > latest_ref_date. This avoids re-inserting ~750 existing
    rows on every sync. When force=True, full-refresh (DELETE + re-INSERT)
    to handle corrections.

    [Phase 3, Commit 1] B4 stale-row cleanup is ENABLED for force=True:
    existing fluxo_observations rows are DELETEd before the new INSERT
    batch. This removes stale trading-day rows when DDM drops them from
    the page (full-refresh pattern, same as acoes + dividends).
    """
    # [I12] Incremental sync: check latest ref_date in DB.
    latest_in_db = _get_latest_ref_date() if not force else ""

    # Fetch + parse (always — the page is small, ~750 rows).
    page = fetch_fluxo_page(force=force)
    if page.get("status") != "ok":
        return page

    observations = parse_fluxo_table(page.get("html", ""))
    now = _SyncEngine._now()

    # [I12] Filter to only new rows (ref_date > latest_in_db).
    # When force=True or DB is empty, latest_in_db="" so all rows pass.
    if latest_in_db:
        new_obs = [o for o in observations if o.get("ref_date", "") > latest_in_db]
        skipped = len(observations) - len(new_obs)
        if skipped > 0:
            _SyncEngine._progress(
                f"[ddm.fluxo] Incremental sync: {len(new_obs)} new rows "
                f"(skipped {skipped} existing, latest_in_db={latest_in_db})"
            )
        observations = new_obs

    last_date = _compute_last_date(observations) or latest_in_db

    # If no new rows, skip the DB write entirely.
    if not observations:
        _SyncEngine._progress(
            f"[ddm.fluxo] No new rows to sync (latest_in_db={latest_in_db})"
        )
        return {
            "status": "ok",
            "rows": 0,
            "last_date": latest_in_db,
            "synced_at": now,
            "skipped": True,
        }

    # Write to DB.
    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        if force:
            # Full-refresh: DELETE all + re-INSERT (handles corrections).
            conn.execute("BEGIN")
            conn.execute("DELETE FROM fluxo_observations")
            try:
                rows = [_row_mapper(obs, now) for obs in observations]
                conn.executemany(_INSERT_SQL, rows)
                _SyncEngine._record_sync_state(conn, "fluxo", last_date, len(observations), now)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        else:
            # Incremental: INSERT OR REPLACE only new rows (no DELETE).
            rows = [_row_mapper(obs, now) for obs in observations]
            conn.executemany(_INSERT_SQL, rows)
            _SyncEngine._record_sync_state(conn, "fluxo", last_date, len(observations), now)
            conn.commit()
    finally:
        conn.close()

    _SyncEngine._progress(
        f"[ddm.fluxo] sync_all: {len(rows)} observations synced"
        + (f" (last_date={last_date})" if last_date else "")
    )

    result: dict = {
        "status": "ok",
        "rows": len(rows),
        "synced_at": now,
    }
    result.update(_result_extras(observations, last_date, now))
    return result

