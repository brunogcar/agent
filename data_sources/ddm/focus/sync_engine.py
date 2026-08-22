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
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from data_sources.ddm.focus.catalog import (
    connect, ensure_schema,
)
from data_sources.ddm.focus.fetcher import fetch_focus_page, parse_focus_tables


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_date() -> str:
    """Return today's date as YYYY-MM-DD (local)."""
    return datetime.now().strftime("%Y-%m-%d")


def _record_sync_state(conn, slug: str, observations: list[dict],
                       now: str, ref_date: str) -> None:
    """Write (or update) the sync_state row for the focus page.

    last_date is the ref_date of THIS sync (today's date in YYYY-MM-DD).
    row_count is the number of rows inserted for this ref_date.
    """
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(slug, last_date, synced_at, row_count) "
        "VALUES (?, ?, ?, ?)",
        (slug, ref_date, now, len(observations)),
    )


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
    """
    page = fetch_focus_page(force=force)
    if page.get("status") != "ok":
        return page

    observations = parse_focus_tables(page.get("html", ""))
    now = _now()
    ref_date = _today_date()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        rows = [
            (o["year"], o["indicator"], o.get("four_weeks_ago"),
             o.get("one_week_ago"), o.get("today"), o.get("comparison"),
             o.get("respondents"), ref_date, now)
            for o in observations
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO focus_observations "
            "(year, indicator, four_weeks_ago, one_week_ago, today, "
            " comparison, respondents, ref_date, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        _record_sync_state(conn, "focus", observations, now, ref_date)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[ddm.focus] sync_all: {len(rows)} observations synced "
              f"(ref_date={ref_date})")
    return {
        "status":    "ok",
        "rows":      len(rows),
        "ref_date":  ref_date,
        "synced_at": now,
    }


def sync_index(slug: str = "focus", force: bool = False) -> dict:
    """Alias for sync_all (parity with the other DDM sub-domains).

    The focus page is single-page (not per-index), so `slug` is ignored
    (only 'focus' is supported). Kept for API symmetry with inflation /
    juros / poupanca / acoes which have a real per-index sync.

    Args:
        slug:  Ignored (kept for API parity). Defaults to 'focus'.
        force: Re-fetch even if recently synced.

    Returns:
        Same shape as sync_all().
    """
    return sync_all(force=force)
