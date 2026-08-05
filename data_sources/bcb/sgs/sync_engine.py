"""data_sources/bcb/sgs/sync_engine.py -- Sync BCB SGS data to local SQLite.

Three sync entry points:
  1. sync_series(code, force=False)   - sync one series (full available history)
  2. sync_all(force=False)             - sync every series in SERIES_CATALOG
                                        (concurrent via fetch_series_concurrent)
  3. sync_series_range(code, start, end, force=False)
                                       - sync a series for a specific date window

Idempotency: uses INSERT OR REPLACE on (series_code, ref_date) primary key.
Re-syncing a series replaces existing rows rather than appending duplicates.

[v3] sync_state uses the v1 schema (series_code, last_date, synced_at,
row_count) instead of v2's generic (key, value, synced_at). This gives
us structured per-series metadata that status_reporter can query directly
without parsing key strings.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from data_sources.bcb.sgs.catalog import (
    SERIES_CATALOG, connect, ensure_schema,
)
from data_sources.bcb.sgs.fetcher import fetch_series, fetch_series_concurrent


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_sync_state(conn, series_code: int, observations: list[dict], now: str,
                       key_suffix: str = "") -> None:
    """Write (or update) the sync_state row for a series.

    [v3] sync_state columns: series_code, last_date, synced_at, row_count.
    `series_code` is stored as TEXT (e.g. "11" or "11:2024-01-01:2024-12-31"
    for range syncs) so we can record both full-sync and range-sync metadata.
    """
    last_date = ""
    if observations:
        last_date = max(o.get("ref_date", "") for o in observations)
    conn.execute(
        "INSERT OR REPLACE INTO sync_state "
        "(series_code, last_date, synced_at, row_count) "
        "VALUES (?, ?, ?, ?)",
        (f"{series_code}{key_suffix}", last_date, now, len(observations)),
    )


def sync_series(code: int, force: bool = False) -> dict:
    """Sync one series from BCB SGS into sgs.db.

    Args:
        code:  BCB SGS series code (must be in SERIES_CATALOG).
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"partial"|"error", "code": <int>, "rows": <int>,
         "synced_at": <iso>}
    """
    if code not in SERIES_CATALOG:
        return {"status": "error", "code": code,
                "error": f"Series {code} not in SERIES_CATALOG"}

    result = fetch_series(code, force=force)
    if result.get("status") != "ok":
        return result

    observations = result.get("observations", [])
    now = _now()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        rows = [
            (code, obs["ref_date"], obs["value"], now)
            for obs in observations
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO series_observations "
            "(series_code, ref_date, value, synced_at) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        _record_sync_state(conn, code, observations, now)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[bcb.sgs] Series {code}: {len(rows)} observations synced")
    return {"status": "ok", "code": code, "rows": len(rows), "synced_at": now}


def sync_all(force: bool = False) -> dict:
    """Sync EVERY series in SERIES_CATALOG concurrently (Semaphore(5)).

    Args:
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"partial", "series_synced": <int>,
         "series_failed": <int>, "rows_total": <int>,
         "results": {code: sync_result, ...}}
    """
    codes = list(SERIES_CATALOG.keys())
    fetch_results = fetch_series_concurrent(codes, force=force)
    now = _now()

    series_synced = 0
    series_failed = 0
    rows_total = 0
    per_series: dict[int, dict] = {}

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        for code, fetched in fetch_results.items():
            if fetched.get("status") != "ok":
                series_failed += 1
                per_series[code] = fetched
                continue
            observations = fetched.get("observations", [])
            rows = [
                (code, obs["ref_date"], obs["value"], now)
                for obs in observations
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO series_observations "
                "(series_code, ref_date, value, synced_at) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            _record_sync_state(conn, code, observations, now)
            series_synced += 1
            rows_total += len(rows)
            per_series[code] = {"status": "ok", "code": code,
                                "rows": len(rows), "synced_at": now}
        conn.commit()
    finally:
        conn.close()

    status = "ok" if series_failed == 0 else "partial"
    _progress(f"[bcb.sgs] sync_all: {series_synced}/{len(codes)} series, "
              f"{rows_total} total rows ({series_failed} failed)")
    return {
        "status": status,
        "series_synced": series_synced,
        "series_failed": series_failed,
        "rows_total": rows_total,
        "results": per_series,
        "synced_at": now,
    }


def sync_series_range(code: int, start: str, end: str,
                      force: bool = False) -> dict:
    """Sync one series for a specific date window [start, end].

    Args:
        code:  BCB SGS series code.
        start: Start date YYYY-MM-DD.
        end:   End date YYYY-MM-DD.
        force: Re-fetch even if recently synced.

    Returns:
        {"status": "ok"|"error", "code": <int>, "rows": <int>,
         "synced_at": <iso>}
    """
    if code not in SERIES_CATALOG:
        return {"status": "error", "code": code,
                "error": f"Series {code} not in SERIES_CATALOG"}
    if not start or not end:
        return {"status": "error", "code": code,
                "error": "start and end (YYYY-MM-DD) are required"}

    result = fetch_series(code, start=start, end=end, force=force)
    if result.get("status") != "ok":
        return result

    observations = result.get("observations", [])
    now = _now()

    conn = connect(read_only=False)
    ensure_schema(conn)
    try:
        rows = [
            (code, obs["ref_date"], obs["value"], now)
            for obs in observations
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO series_observations "
            "(series_code, ref_date, value, synced_at) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        # Range syncs use a suffixed key so they don't overwrite the
        # full-sync metadata (e.g. "11:2024-01-01:2024-12-31").
        key_suffix = f":{start}:{end}"
        _record_sync_state(conn, code, observations, now, key_suffix=key_suffix)
        conn.commit()
    finally:
        conn.close()

    _progress(f"[bcb.sgs] Series {code} [{start}..{end}]: {len(rows)} rows")
    return {"status": "ok", "code": code, "rows": len(rows),
            "start": start, "end": end, "synced_at": now}
