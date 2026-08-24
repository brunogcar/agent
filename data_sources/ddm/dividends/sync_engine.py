"""data_sources/ddm/dividends/sync_engine.py -- Sync DDM dividends to SQLite.

Two sync entry points (mirror the ddm/juros + ddm/poupanca pattern):
  1. sync_index(slug='dividends', force=False) - alias for sync_all (single
       page = single slug).
  2. sync_all(force=False) - fetch + parse + store the dividend agenda page.

Idempotency: uses INSERT OR REPLACE on (ticker, record_date, tipo) primary key.
Re-syncing replaces existing rows rather than appending duplicates.

[Phase 3, Commit 1] Refactored to delegate to `data_sources/ddm/_base/`
(BaseDDMSyncEngine.sync_single_page). The fetch + parse + DELETE + INSERT
+ sync_state pattern now lives in _base/sync_base.py; this module keeps
only the per-source config (fetcher fn, parser fn, INSERT SQL, row
mapper, B4 full-refresh flag, last_date computation) + the sync_index()
alias with dividends-specific slug validation.
"""

from __future__ import annotations

from data_sources.ddm._base.sync_base import BaseDDMSyncEngine
from data_sources.ddm.dividends.catalog import connect, ensure_schema
from data_sources.ddm.dividends.fetcher import (
    fetch_dividends_page, parse_dividends_table,
)

class _SyncEngine(BaseDDMSyncEngine):
    """Dividends-specific sync engine config (SOURCE_NAME for log prefix)."""

    SOURCE_NAME = "dividends"

_INSERT_SQL = (
    "INSERT OR REPLACE INTO dividends "
    "(ticker, tipo, value, record_date, ex_date, payment_date, synced_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

def _row_mapper(row: dict, now: str) -> tuple:
    return (
        row["ticker"], row.get("tipo"), row.get("value"),
        row.get("record_date"), row.get("ex_date"), row.get("payment_date"), now,
    )

def _compute_last_date(rows: list[dict]) -> str:
    """last_date = latest record_date (string comparison works for YYYY-MM-DD)."""
    if not rows:
        return ""
    return max((r.get("record_date") or "") for r in rows)

def sync_all(force: bool = False) -> dict:
    """Sync the entire dividend agenda page into dividends.db.

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok", "rows": <int>, "synced_at": <iso>}
    """
    return _SyncEngine.sync_single_page(
        fetch_fn=fetch_dividends_page,
        parse_fn=parse_dividends_table,
        connect_fn=connect,
        ensure_schema_fn=ensure_schema,
        insert_sql=_INSERT_SQL,
        row_mapper=_row_mapper,
        slug="dividends",
        table_name="dividends",
        # [v2 fix B4] Full-refresh pattern: delete ALL existing rows before
        # re-inserting. This removes cancelled dividends that DDM dropped
        # from the agenda page (INSERT OR REPLACE only touches rows in the
        # new payload, leaving stale rows behind).
        full_refresh=True,
        compute_last_date=_compute_last_date,
        force=force,
    )

