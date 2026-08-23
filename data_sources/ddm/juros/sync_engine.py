"""data_sources/ddm/juros/sync_engine.py -- Sync DDM juros data to SQLite.

Two sync entry points:
  1. sync_index(slug, force=False)  - sync one index (matrix only; the
                                       historical series is DERIVED from the
                                       matrix at parse time)
  2. sync_all(force=False)          - sync every index in JUROS_CATALOG
                                       (concurrent via ThreadPoolExecutor,
                                       max_workers=3)

Idempotency: uses INSERT OR REPLACE on (slug, ref_date) primary key.
Re-syncing an index replaces existing rows rather than appending duplicates.

[Phase 3, Commit 1] Refactored to delegate to `data_sources/ddm/_base/`
(BaseDDMSyncEngine.sync_multi_page). The TPE + as_completed + sequential
DB-write pattern now lives in _base/sync_base.py; this module keeps only
the per-source config (JUROS_CATALOG, fetcher fn, parser pipeline,
INSERT SQL, row mapper) + the sync_index() entry point (which has
juros-specific slug validation + the matrix-flatten pipeline).
"""

from __future__ import annotations

from data_sources.ddm._base.sync_base import BaseDDMSyncEngine
from data_sources.ddm.juros.catalog import (
    JUROS_CATALOG, connect, ensure_schema,
)
from data_sources.ddm.juros.fetcher import (
    fetch_juros_page, flatten_matrix_to_observations, parse_matrix_only,
)


class _SyncEngine(BaseDDMSyncEngine):
    """Juros-specific sync engine config (SOURCE_NAME for log prefix)."""

    SOURCE_NAME = "juros"


# SQL + row mapper shared by sync_index + sync_all.
_INSERT_SQL = (
    "INSERT OR REPLACE INTO juros_observations "
    "(slug, ref_date, month_value, media_no_ano, media_12m, synced_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


def _row_mapper(obs: dict, slug: str, now: str) -> tuple:
    return (
        slug, obs["ref_date"], obs.get("month_value"),
        obs.get("media_no_ano"), obs.get("media_12m"), now,
    )


def _parse_pipeline(html: str) -> list[dict]:
    """juros pipeline: parse_matrix_only -> flatten_matrix_to_observations."""
    matrix = parse_matrix_only(html)
    return flatten_matrix_to_observations(matrix)


def sync_index(slug: str, force: bool = False) -> dict:
    """Sync one index from DDM into juros.db.

    Pipeline: fetch HTML -> parse_matrix_only -> flatten_matrix_to_observations
    -> INSERT OR REPLACE into juros_observations.

    Args:
        slug:  DDM juros slug (must be in JUROS_CATALOG).
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "slug": <str>, "rows": <int>,
         "synced_at": <iso>}
    """
    if slug not in JUROS_CATALOG:
        return {"status": "error", "slug": slug,
                "error": f"Index '{slug}' not in JUROS_CATALOG. "
                         f"Available: {list(JUROS_CATALOG.keys())}"}

    page = fetch_juros_page(slug, force=force)
    if page.get("status") != "ok":
        return page

    observations = _parse_pipeline(page.get("html", ""))
    now = _SyncEngine._now()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        rows = [_row_mapper(obs, slug, now) for obs in observations]
        conn.executemany(_INSERT_SQL, rows)
        last_date = ""
        if observations:
            last_date = max((o.get("ref_date", "") for o in observations),
                            default="")
        _SyncEngine._record_sync_state(
            conn, slug, last_date, len(observations), now,
        )
        conn.commit()
    finally:
        conn.close()

    _SyncEngine._progress(
        f"[ddm.juros] Index {slug}: {len(rows)} observations derived + synced"
    )
    return {"status": "ok", "slug": slug, "rows": len(rows), "synced_at": now}


def sync_all(force: bool = False) -> dict:
    """Sync EVERY index in JUROS_CATALOG concurrently (max_workers=3).

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"partial", "indices_synced": <int>,
         "indices_failed": <int>, "rows_total": <int>,
         "results": {slug: sync_result, ...}}
    """
    return _SyncEngine.sync_multi_page(
        catalog=JUROS_CATALOG,
        fetch_fn=fetch_juros_page,
        parse_pipeline_fn=_parse_pipeline,
        connect_fn=connect,
        ensure_schema_fn=ensure_schema,
        insert_sql=_INSERT_SQL,
        row_mapper=_row_mapper,
        force=force,
    )
