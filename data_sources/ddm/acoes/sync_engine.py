"""data_sources/ddm/acoes/sync_engine.py -- Sync DDM acoes data to SQLite.

Two sync entry points:
  1. sync_all(force=False)           - fetch + parse + store the acoes page
                                       (single HTTP call, single page)
  2. sync_index(slug="acoes", force) - alias for sync_all (parity with the
                                       other DDM sub-domains; the acoes page
                                       is single-page, not per-index)

Idempotency: uses INSERT OR REPLACE on the ticker primary key.
Re-syncing replaces existing rows rather than appending duplicates.

[Phase 3, Commit 1] Refactored to delegate to `data_sources/ddm/_base/`
(BaseDDMSyncEngine.sync_single_page). The fetch + parse + DELETE + INSERT
+ sync_state pattern now lives in _base/sync_base.py; this module keeps
only the per-source config (fetcher fn, parser fn, INSERT SQL, row
mapper, B4 full-refresh flag, last_date computation) + the sync_index()
alias.
"""

from __future__ import annotations

from data_sources.ddm._base.sync_base import BaseDDMSyncEngine
from data_sources.ddm.acoes.catalog import (
    connect, ensure_schema,
)
from data_sources.ddm.acoes.fetcher import fetch_acoes_page, parse_stocks_table


class _SyncEngine(BaseDDMSyncEngine):
    """Acoes-specific sync engine config (SOURCE_NAME for log prefix)."""

    SOURCE_NAME = "acoes"


_INSERT_SQL = (
    "INSERT OR REPLACE INTO stocks "
    "(ticker, name, negocios, last_price, variation, synced_at, ref_date) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


def _row_mapper(stock: dict, now: str) -> tuple:
    """Map a parsed stock dict to the INSERT SQL tuple shape.

    ref_date is the scrape date (acoes has no per-row ref_date in the
    payload -- DDM does not expose a "data do pregao" column).
    """
    ref_date = _SyncEngine._today_date()
    return (
        stock["ticker"], stock.get("name"), stock.get("negocios"),
        stock.get("last_price"), stock.get("variation"), now, ref_date,
    )


def _compute_last_date(observations: list[dict]) -> str:
    """last_date = today's date (the scrape date).

    The acoes page has no per-row ref_date; the sync_state.last_date is
    the day the snapshot was scraped.
    """
    return _SyncEngine._today_date()


def sync_all(force: bool = False) -> dict:
    """Sync the /acoes page into acoes.db.

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "rows": <int>, "synced_at": <iso>}
    """
    return _SyncEngine.sync_single_page(
        fetch_fn=fetch_acoes_page,
        parse_fn=parse_stocks_table,
        connect_fn=connect,
        ensure_schema_fn=ensure_schema,
        insert_sql=_INSERT_SQL,
        row_mapper=_row_mapper,
        slug="acoes",
        table_name="stocks",
        # [v2 fix B4] Full-refresh pattern: delete ALL existing rows before
        # re-inserting. This removes delisted stocks that DDM dropped from
        # the /acoes page (INSERT OR REPLACE only touches rows in the new
        # payload, leaving stale rows behind).
        full_refresh=True,
        compute_last_date=_compute_last_date,
        force=force,
    )


def sync_index(slug: str = "acoes", force: bool = False) -> dict:
    """Alias for sync_all (parity with the other DDM sub-domains).

    The acoes page is single-page (not per-index), so `slug` is ignored
    (only 'acoes' is supported). Kept for API symmetry with inflation /
    juros / poupanca which have a real per-index sync.

    Args:
        slug:  Ignored (kept for API parity). Defaults to 'acoes'.
        force: Re-fetch even if recently synced.

    Returns:
        Same shape as sync_all().
    """
    return sync_all(force=force)
