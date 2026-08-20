"""data_sources/ddm/poupanca/sync_engine.py -- Sync DDM poupanca data to SQLite.

Two sync entry points:
  1. sync_index(slug, force=False)  - sync one index (matrix only; the
                                       historical series is DERIVED from the
                                       matrix at parse time using SUM)
  2. sync_all(force=False)          - sync every index in POUPANCA_CATALOG
                                       (concurrent via ThreadPoolExecutor,
                                       max_workers=3)

Idempotency: uses INSERT OR REPLACE on (slug, ref_date) primary key.
Re-syncing an index replaces existing rows rather than appending duplicates.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from data_sources.ddm.poupanca.catalog import (
    POUPANCA_CATALOG, connect, ensure_schema,
)
from data_sources.ddm.poupanca.fetcher import (
    fetch_poupanca_page, parse_matrix_only, flatten_matrix_to_observations,
)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_sync_state(conn, slug: str, observations: list[dict], now: str) -> None:
    """Write (or update) the sync_state row for an index."""
    last_date = ""
    if observations:
        last_date = max(o.get("ref_date", "") for o in observations)
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(slug, last_date, synced_at, row_count) "
        "VALUES (?, ?, ?, ?)",
        (slug, last_date, now, len(observations)),
    )


def sync_index(slug: str, force: bool = False) -> dict:
    """Sync one index from DDM into poupanca.db.

    Pipeline: fetch HTML -> parse_matrix_only -> flatten_matrix_to_observations
    -> INSERT OR REPLACE into poupanca_observations.

    Args:
        slug:  DDM poupanca slug (must be in POUPANCA_CATALOG).
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "slug": <str>, "rows": <int>,
         "synced_at": <iso>}
    """
    if slug not in POUPANCA_CATALOG:
        return {"status": "error", "slug": slug,
                "error": f"Index '{slug}' not in POUPANCA_CATALOG. "
                         f"Available: {list(POUPANCA_CATALOG.keys())}"}

    page = fetch_poupanca_page(slug, force=force)
    if page.get("status") != "ok":
        return page

    matrix = parse_matrix_only(page.get("html", ""))
    observations = flatten_matrix_to_observations(matrix)
    now = _now()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        rows = [
            (slug, obs["ref_date"], obs.get("month_value"),
             obs.get("acumulado_no_ano"), obs.get("acumulado_12m"), now)
            for obs in observations
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO poupanca_observations "
            "(slug, ref_date, month_value, acumulado_no_ano, acumulado_12m, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        _record_sync_state(conn, slug, observations, now)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[ddm.poupanca] Index {slug}: {len(rows)} observations derived + synced")
    return {"status": "ok", "slug": slug, "rows": len(rows), "synced_at": now}


def sync_all(force: bool = False) -> dict:
    """Sync EVERY index in POUPANCA_CATALOG concurrently (max_workers=3).

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"partial", "indices_synced": <int>,
         "indices_failed": <int>, "rows_total": <int>,
         "results": {slug: sync_result, ...}}
    """
    slugs = list(POUPANCA_CATALOG.keys())
    now = _now()

    index_synced = 0
    index_failed = 0
    rows_total = 0
    per_index: dict[str, dict] = {}

    # Concurrent fetch + parse, then sequential DB writes (single connection).
    fetch_results: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_slug = {
            executor.submit(fetch_poupanca_page, slug, force): slug
            for slug in slugs
        }
        for future in as_completed(future_to_slug):
            slug = future_to_slug[future]
            try:
                page = future.result()
            except Exception as e:
                fetch_results[slug] = []
                per_index[slug] = {"status": "error", "slug": slug,
                                   "error": str(e)}
                index_failed += 1
                continue
            if page.get("status") != "ok":
                fetch_results[slug] = []
                per_index[slug] = page
                index_failed += 1
                continue
            matrix = parse_matrix_only(page.get("html", ""))
            fetch_results[slug] = flatten_matrix_to_observations(matrix)

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        for slug, observations in fetch_results.items():
            if not observations and slug not in per_index:
                # Already errored above; skip.
                continue
            if slug in per_index and per_index[slug].get("status") == "error":
                continue
            rows = [
                (slug, obs["ref_date"], obs.get("month_value"),
                 obs.get("acumulado_no_ano"), obs.get("acumulado_12m"), now)
                for obs in observations
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO poupanca_observations "
                "(slug, ref_date, month_value, acumulado_no_ano, acumulado_12m, synced_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            _record_sync_state(conn, slug, observations, now)
            index_synced += 1
            rows_total += len(rows)
            per_index[slug] = {"status": "ok", "slug": slug,
                               "rows": len(rows), "synced_at": now}
        conn.commit()
    finally:
        conn.close()

    status = "ok" if index_failed == 0 else "partial"
    _progress(f"[ddm.poupanca] sync_all: {index_synced}/{len(slugs)} indices, "
              f"{rows_total} total rows ({index_failed} failed)")
    return {
        "status":         status,
        "indices_synced": index_synced,
        "indices_failed": index_failed,
        "rows_total":     rows_total,
        "results":        per_index,
        "synced_at":      now,
    }
