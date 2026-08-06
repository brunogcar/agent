"""data_sources/bcb/sgs/fetcher.py -- HTTP fetcher for BCB SGS API.

Handles:
  - HTTP GET to api.bcb.gov.br (no auth, no token)
  - Strict date normalization: DD/MM/YYYY (BCB format) -> YYYY-MM-DD at the
    ingest boundary (cnpj_digits-style pattern - never store raw DD/MM/YYYY).
  - String -> float parsing (BCB returns `valor` as STRING).
  - Thread-safe in-memory cache (5-min TTL, Lock-guarded).
  - Concurrency limiting via a Semaphore(5) - mirrors brapi v1.1 pattern.

NO local database writes - this module only fetches. sync_engine.py stores.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from data_sources.bcb.sgs.catalog import series_url, series_last_url

# 5-minute cache TTL. BCB publishes daily series once per business day, so 5min
# is well within the freshness window. Cache is per-series + per-window.
_CACHE_TTL = 300

_cache: dict[str, tuple[object, float]] = {}

# Thread-safety primitives (mirror brapi fetcher):
#   _cache_lock             - guards all reads/writes to the _cache dict
#   _concurrency_semaphore  - caps in-flight HTTP requests to 5 (BCB has no
#                             documented rate limit; this is conservative)
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(5)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_date(dmy: str) -> str:
    """Convert DD/MM/YYYY -> YYYY-MM-DD.

    BCB returns dates as DD/MM/YYYY strings. We normalize at the fetcher
    boundary so nothing downstream ever sees a DD/MM/YYYY string.

    Returns "" if the input is empty or unparseable.
    """
    if not dmy:
        return ""
    try:
        dt = datetime.strptime(dmy, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _parse_value(raw) -> float | None:
    """Parse BCB `valor` (string, comma decimal) -> float.

    BCB returns Portuguese-formatted numbers like "10,234567". We replace
    comma with dot and float()-parse. Returns None on failure.
    """
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace(",", "."))
    except (ValueError, TypeError):
        return None


def fetch_series(code: int, start: str = "", end: str = "",
                 force: bool = False) -> dict:
    """Fetch observations for a series between start/end (YYYY-MM-DD).

    Args:
        code:  BCB SGS series code (e.g. 11 = Selic diaria).
        start: Start date YYYY-MM-DD (optional - empty = all available).
        end:   End date YYYY-MM-DD (optional - empty = today).
        force: Bypass cache.

    Returns:
        {"status": "ok", "code": <int>, "count": <int>,
         "observations": [{"ref_date": "YYYY-MM-DD", "value": <float>}, ...]}
    """
    cache_key = f"series:{code}:{start}:{end}"

    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                return data

    # Build URL. BCB expects DD/MM/YYYY in query params; convert from our
    # internal YYYY-MM-DD representation.
    # [v4] ALWAYS include date params - BCB API returns 406 Not Acceptable
    # for daily series when no date range is specified.
    url = series_url(code)
    now = datetime.now()
    if not end:
        end = now.strftime("%Y-%m-%d")
    if not start:
        # [v4 P1] Use timedelta, not .replace(year=...), to avoid Feb 29 crash
        from datetime import timedelta
        start = (now - timedelta(days=5 * 365)).strftime("%Y-%m-%d")
    params = {
        "formato": "json",
        "dataInicial": datetime.strptime(start, "%Y-%m-%d").strftime("%d/%m/%Y"),
        "dataFinal": datetime.strptime(end, "%Y-%m-%d").strftime("%d/%m/%Y"),
    }
    headers = {"Accept": "application/json"}

    _progress(f"[bcb.sgs] Fetching series {code} ({start} -> {end})")

    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "code": code, "error": f"bcb.sgs: {e}"}

    try:
        data = resp.json()
    except ValueError as e:
        return {"status": "error", "code": code, "error": f"bcb.sgs: invalid JSON - {e}"}

    if not isinstance(data, list):
        # BCB returns "Value(s) not found" or similar for unknown series.
        return {"status": "not_found", "code": code,
                "error": f"No data for series {code}"}

    observations = []
    for row in data:
        ref_date = _normalize_date(row.get("data", ""))
        value = _parse_value(row.get("valor"))
        if not ref_date:
            continue  # skip rows with unparseable dates
        observations.append({"ref_date": ref_date, "value": value})

    result = {"status": "ok", "code": code, "count": len(observations),
              "observations": observations, "synced_at": _now_iso()}

    with _cache_lock:
        _cache[cache_key] = (result, time.time())
    return result


def fetch_series_concurrent(codes: list[int], start: str = "", end: str = "",
                            force: bool = False) -> dict[int, dict]:
    """Fetch multiple series CONCURRENTLY (up to 5 at a time via Semaphore).

    Args:
        codes: List of BCB SGS series codes.
        start: Start date YYYY-MM-DD (optional).
        end:   End date YYYY-MM-DD (optional).
        force: Bypass cache.

    Returns:
        {code: fetch_result, ...} - one entry per code.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_code = {
            executor.submit(fetch_series, c, start, end, force): c
            for c in codes
        }
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                results[code] = future.result()
            except Exception as e:
                results[code] = {"status": "error", "code": code, "error": str(e)}
    return results


def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    with _cache_lock:
        _cache.clear()
