"""data_sources/ddm/acoes/sync_engine.py -- Sync DDM acoes data to SQLite.

Two sync entry points:
  1. sync_all(force=False)           - fetch + parse + store the acoes page
                                       (single HTTP call, single page)
  2. sync_index(slug="acoes", force) - alias for sync_all (parity with the
                                       other DDM sub-domains; the acoes page
                                       is single-page, not per-index)

Idempotency: uses INSERT OR REPLACE on the ticker primary key.
Re-syncing replaces existing rows rather than appending duplicates.

[v2] EVOLUTION STORE -- the acoes page is a LIVE quote table with no
history (unlike inflation/juros/poupanca, whose pages carry full series),
so the only way to chart how the price distribution moves over time is to
ACCUMULATE one snapshot per sync ourselves. Every sync_all() now ALSO
writes the day's rows into stocks_history keyed by (ref_date, ticker):
  - re-syncing the SAME day replaces that day's snapshot (idempotent);
  - a sync on a NEW day adds one snapshot (the series grows, one per day);
  - the FIRST sync after upgrading a pre-v2 DB also preserves the previous
    `stocks` snapshot into stocks_history (read BEFORE the full-refresh
    DELETE wipes it), so the evolution starts with the data the user
    already has instead of from zero.
Both history writes run inside the SAME transaction as the main stocks
INSERT (the v2 extra_write_fn hook in BaseDDMSyncEngine.sync_single_page)
-- a failure rolls the whole sync back.

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

# [v2] The evolution store: one row per ticker per snapshot date.
_HISTORY_INSERT_SQL = (
    "INSERT OR REPLACE INTO stocks_history "
    "(ref_date, ticker, name, negocios, last_price, variation, synced_at) "
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


# ── [v2] evolution store helpers ─────────────────────────────────────────────

def _read_current_snapshot() -> list[tuple]:
    """Read the pre-refresh `stocks` rows, as history INSERT tuples.

    Runs BEFORE sync_single_page's full-refresh DELETE wipes the table.
    The rows keep their OWN ref_date -- the snapshot the user already has
    becomes the first point of the evolution (first sync after upgrade).
    Non-fatal on any failure (missing DB, pre-schema DB, locked file): a
    [] backfill just means the history starts with today's snapshot.
    """
    try:
        conn = connect(read_only=True)
    except Exception:
        return []
    try:
        rows = conn.execute(
            "SELECT ref_date, ticker, name, negocios, last_price, "
            "variation, synced_at FROM stocks WHERE ref_date IS NOT NULL"
        ).fetchall()
        return [tuple(r) for r in rows]
    except Exception:
        # Pre-schema DB (no stocks table yet) or unreadable -- start today.
        return []
    finally:
        conn.close()


def _make_extra_write_fn(preserved: list[tuple]):
    """Build the in-transaction history writer (the v2 evolution store).

    Called by sync_single_page INSIDE the main transaction, after the
    stocks INSERT:
      (a) backfill the preserved pre-refresh snapshot under its OWN
          ref_date (first-sync-after-upgrade preservation);
      (b) append TODAY's observations -- INSERT OR REPLACE keyed
          (ref_date, ticker): same-day re-syncs replace that day's
          snapshot, a new day adds one. Written AFTER the backfill so a
          preserved row sharing today's date loses to the fresh value.
    """
    def _write_history(conn, observations: list[dict], now: str,
                       last_date: str) -> None:
        if preserved:
            conn.executemany(_HISTORY_INSERT_SQL, preserved)
        ref_date = last_date or _SyncEngine._today_date()
        conn.executemany(_HISTORY_INSERT_SQL, [
            (ref_date, o["ticker"], o.get("name"), o.get("negocios"),
             o.get("last_price"), o.get("variation"), now)
            for o in observations
        ])
    return _write_history


def sync_all(force: bool = False) -> dict:
    """Sync the /acoes page into acoes.db (+ stocks_history snapshot).

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "rows": <int>, "synced_at": <iso>}
    """
    # [v2] Read the existing snapshot BEFORE the full-refresh DELETE --
    # preserved into stocks_history so the evolution keeps it.
    preserved = _read_current_snapshot()
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
        extra_write_fn=_make_extra_write_fn(preserved),
        force=force,
    )
