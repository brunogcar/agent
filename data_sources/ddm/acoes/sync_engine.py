"""data_sources/ddm/acoes/sync_engine.py -- Sync DDM acoes data to SQLite.

Two sync entry points:
  1. sync_all(force=False)           - fetch + parse + store the acoes page
                                       (single HTTP call, single page)
  2. sync_index(slug="acoes", force) - alias for sync_all (parity with the
                                       other DDM sub-domains; the acoes page
                                       is single-page, not per-index)

Idempotency: uses INSERT OR REPLACE on the ticker primary key.
Re-syncing replaces existing rows rather than appending duplicates.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from data_sources.ddm.acoes.catalog import (
    connect, ensure_schema,
)
from data_sources.ddm.acoes.fetcher import fetch_acoes_page, parse_stocks_table


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_date() -> str:
    """Return today's date as YYYY-MM-DD (local)."""
    return datetime.now().strftime("%Y-%m-%d")


def _record_sync_state(conn, slug: str, stocks: list[dict], now: str) -> None:
    """Write (or update) the sync_state row for the acoes page."""
    last_date = _today_date()
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(slug, last_date, synced_at, row_count) "
        "VALUES (?, ?, ?, ?)",
        (slug, last_date, now, len(stocks)),
    )


def sync_all(force: bool = False) -> dict:
    """Sync the /acoes page into acoes.db.

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "rows": <int>, "synced_at": <iso>}
    """
    page = fetch_acoes_page(force=force)
    if page.get("status") != "ok":
        return page

    stocks = parse_stocks_table(page.get("html", ""))
    now = _now()
    ref_date = _today_date()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        # [v2 fix B4] Full-refresh pattern: delete ALL existing rows before
        # re-inserting. This removes delisted stocks that DDM dropped from
        # the /acoes page (INSERT OR REPLACE only touches rows in the new
        # payload, leaving stale rows behind).
        conn.execute("DELETE FROM stocks")
        rows = [
            (s["ticker"], s.get("name"), s.get("negocios"),
             s.get("last_price"), s.get("variation"), now, ref_date)
            for s in stocks
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO stocks "
            "(ticker, name, negocios, last_price, variation, synced_at, ref_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        _record_sync_state(conn, "acoes", stocks, now)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[ddm.acoes] sync_all: {len(rows)} stocks synced")
    return {"status": "ok", "rows": len(rows), "synced_at": now}


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
