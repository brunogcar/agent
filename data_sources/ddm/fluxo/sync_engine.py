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
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from data_sources.ddm.fluxo.catalog import (
    connect, ensure_schema,
)
from data_sources.ddm.fluxo.fetcher import fetch_fluxo_page, parse_fluxo_table


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_sync_state(conn, slug: str, observations: list[dict],
                       now: str, last_date: str) -> None:
    """Write (or update) the sync_state row for the fluxo page.

    last_date is the most recent ref_date in the synced observations
    (the newest trading day). row_count is the number of rows synced.
    """
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(slug, last_date, synced_at, row_count) "
        "VALUES (?, ?, ?, ?)",
        (slug, last_date, now, len(observations)),
    )


def sync_all(force: bool = False) -> dict:
    """Sync the /fluxo page into fluxo.db.

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "rows": <int>, "last_date": <str>,
         "synced_at": <iso>}

    The sync is a single HTTP call (no ThreadPoolExecutor needed - the
    fluxo page is one document, not per-index). All parsed observations
    are INSERTed OR REPLACEd into fluxo.db, keyed by ref_date. Earlier
    ref_dates are preserved so consumers can query the history of daily
    investment flow over time.
    """
    page = fetch_fluxo_page(force=force)
    if page.get("status") != "ok":
        return page

    observations = parse_fluxo_table(page.get("html", ""))
    now = _now()

    # last_date = the most recent ref_date in the synced observations.
    # The /fluxo page is DESC (newest first), so the first observation
    # is the most recent trading day.
    last_date = ""
    if observations:
        last_date = max(o["ref_date"] for o in observations
                        if o.get("ref_date"))

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        rows = [
            (o["ref_date"], o.get("estrangeiro"), o.get("institucional"),
             o.get("pessoa_fisica"), o.get("inst_financeira"),
             o.get("outros"), now)
            for o in observations
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO fluxo_observations "
            "(ref_date, estrangeiro, institucional, pessoa_fisica, "
            " inst_financeira, outros, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        _record_sync_state(conn, "fluxo", observations, now, last_date)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[ddm.fluxo] sync_all: {len(rows)} observations synced "
              f"(last_date={last_date})")
    return {
        "status":    "ok",
        "rows":      len(rows),
        "last_date": last_date,
        "synced_at": now,
    }


def sync_index(slug: str = "fluxo", force: bool = False) -> dict:
    """Alias for sync_all (parity with the other DDM sub-domains).

    The fluxo page is single-page (not per-index), so `slug` is ignored
    (only 'fluxo' is supported). Kept for API symmetry with inflation /
    juros / poupanca / acoes / focus which have a real per-index sync.

    Args:
        slug:  Ignored (kept for API parity). Defaults to 'fluxo'.
        force: Re-fetch even if recently synced.

    Returns:
        Same shape as sync_all().
    """
    return sync_all(force=force)
