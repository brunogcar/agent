"""data_sources/ddm/dividends/sync_engine.py -- Sync DDM dividends to SQLite.

Two sync entry points (mirror the ddm/juros + ddm/poupanca pattern):
  1. sync_index(slug='dividends', force=False) - alias for sync_all (single
       page = single slug).
  2. sync_all(force=False) - fetch + parse + store the dividend agenda page.

Idempotency: uses INSERT OR REPLACE on (ticker, record_date, tipo) primary key.
Re-syncing replaces existing rows rather than appending duplicates.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from data_sources.ddm.dividends.catalog import connect, ensure_schema
from data_sources.ddm.dividends.fetcher import (
    fetch_dividends_page, parse_dividends_table,
)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_sync_state(conn, slug: str, rows: list[dict], now: str) -> None:
    """Write (or update) the sync_state row."""
    last_date = ""
    if rows:
        # latest record_date (string comparison works for YYYY-MM-DD).
        last_date = max((r.get("record_date") or "") for r in rows)
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(slug, last_date, synced_at, row_count) "
        "VALUES (?, ?, ?, ?)",
        (slug, last_date, now, len(rows)),
    )


def sync_all(force: bool = False) -> dict:
    """Sync the entire dividend agenda page into dividends.db.

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok", "rows": <int>, "synced_at": <iso>}
    """
    page = fetch_dividends_page(force=force)
    if page.get("status") != "ok":
        return page

    rows = parse_dividends_table(page.get("html", ""))
    now = _now()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        # [v2 fix B4] Full-refresh pattern: delete ALL existing rows before
        # re-inserting. This removes cancelled dividends that DDM dropped
        # from the agenda page (INSERT OR REPLACE only touches rows in the
        # new payload, leaving stale rows behind).
        conn.execute("DELETE FROM dividends")
        tuples = [
            (r["ticker"], r.get("tipo"), r.get("value"),
             r.get("record_date"), r.get("ex_date"), r.get("payment_date"), now)
            for r in rows
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO dividends "
            "(ticker, tipo, value, record_date, ex_date, payment_date, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuples,
        )
        _record_sync_state(conn, "dividends", rows, now)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[ddm.dividends] sync_all: {len(rows)} dividend rows synced")
    return {"status": "ok", "rows": len(rows), "synced_at": now}


def sync_index(slug: str = "dividends", force: bool = False) -> dict:
    """Sync one "index" (the dividends page is a single page; slug must be
    'dividends'). Alias for sync_all.

    Args:
        slug:  Must be 'dividends' (kept for parity with the ddm/juros +
               ddm/poupanca + ddm/inflation sync_index signature).
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok", "slug": "dividends", "rows": <int>, "synced_at": <iso>}
    """
    if slug and slug != "dividends":
        return {"status": "error", "slug": slug,
                "error": f"Unknown slug '{slug}' (only 'dividends' is supported)"}
    out = sync_all(force=force)
    if out.get("status") == "ok":
        out["slug"] = "dividends"
    return out
