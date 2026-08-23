"""data_sources/ddm/inflation/sync_engine.py -- Sync DDM inflation data to SQLite.

Two sync entry points:
  1. sync_index(slug, force=False)  - sync one index (full HTML history)
  2. sync_all(force=False)          - sync every index in INDEX_CATALOG
                                       (concurrent via ThreadPoolExecutor,
                                       max_workers=3)

Idempotency: uses INSERT OR REPLACE on (slug, ref_date) primary key.
Re-syncing an index replaces existing rows rather than appending duplicates.

[Phase 3, Commit 1] Refactored to delegate to `data_sources/ddm/_base/`
(BaseDDMSyncEngine.sync_multi_page). The TPE + as_completed + sequential
DB-write pattern now lives in _base/sync_base.py; this module keeps only
the per-source config (catalog, fetcher fn, parser pipeline, INSERT SQL,
row mapper) + the sync_index() entry point (which has inflation-specific
slug validation).
"""

from __future__ import annotations

from data_sources.ddm._base.sync_base import BaseDDMSyncEngine
from data_sources.ddm.inflation.catalog import (
    INDEX_CATALOG, connect, ensure_schema,
)
from data_sources.ddm.inflation.fetcher import fetch_index_page, parse_historical_table


class _SyncEngine(BaseDDMSyncEngine):
    """Inflation-specific sync engine config (SOURCE_NAME for log prefix)."""

    SOURCE_NAME = "inflation"


# SQL + row mapper shared by sync_index + sync_all.
_INSERT_SQL = (
    "INSERT OR REPLACE INTO index_observations "
    "(slug, ref_date, month_value, year_acumulado, acumulado_12m, synced_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


def _row_mapper(obs: dict, slug: str, now: str) -> tuple:
    return (
        slug, obs["ref_date"], obs.get("month_value"),
        obs.get("year_acumulado"), obs.get("acumulado_12m"), now,
    )


def sync_index(slug: str, force: bool = False) -> dict:
    """Sync one index from DDM into inflation.db.

    Args:
        slug:  DDM index slug (must be in INDEX_CATALOG).
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "slug": <str>, "rows": <int>,
         "synced_at": <iso>}
    """
    if slug not in INDEX_CATALOG:
        return {"status": "error", "slug": slug,
                "error": f"Index '{slug}' not in INDEX_CATALOG. "
                         f"Available: {list(INDEX_CATALOG.keys())}"}

    page = fetch_index_page(slug, force=force)
    if page.get("status") != "ok":
        return page

    observations = parse_historical_table(page.get("html", ""))
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
        f"[ddm.inflation] Index {slug}: {len(rows)} observations synced"
    )
    return {"status": "ok", "slug": slug, "rows": len(rows), "synced_at": now}


def sync_all(force: bool = False) -> dict:
    """Sync EVERY index in INDEX_CATALOG concurrently (max_workers=3).

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"partial", "indices_synced": <int>,
         "indices_failed": <int>, "rows_total": <int>,
         "results": {slug: sync_result, ...}}
    """
    return _SyncEngine.sync_multi_page(
        catalog=INDEX_CATALOG,
        fetch_fn=fetch_index_page,
        parse_pipeline_fn=parse_historical_table,
        connect_fn=connect,
        ensure_schema_fn=ensure_schema,
        insert_sql=_INSERT_SQL,
        row_mapper=_row_mapper,
        force=force,
    )
