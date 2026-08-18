"""data_sources/bcb/focus/fetcher.py -- HTTP fetcher for BCB Focus (Olinda OData).

Handles:
  - HTTP GET to olinda.bcb.gov.br (no auth, no token)
  - Strict date normalization: 'YYYY-MM-DD' is already ISO (Olinda returns
    ISO dates, unlike SGS which returns DD/MM/YYYY).
  - String -> float parsing (Olinda returns numbers as JSON numbers, but
    defensive parsing handles edge cases).
  - Thread-safe in-memory cache (5-min TTL, Lock-guarded).
  - Concurrency limiting via a Semaphore(5) -- mirrors the sgs fetcher pattern.

NO local database writes -- this module only fetches. sync_engine.py stores.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from data_sources.bcb.focus.catalog import endpoint_url

# 5-minute cache TTL. The Focus survey publishes weekly, so 5min is well
# within the freshness window. Cache is per-indicator + per-frequency + top.
_CACHE_TTL = 300

_cache: dict[str, tuple[object, float]] = {}

# Thread-safety primitives (mirror sgs fetcher):
#   _cache_lock             - guards all reads/writes to the _cache dict
#   _concurrency_semaphore  - caps in-flight HTTP requests to 5 (conservative)
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(5)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_date(d: str) -> str:
    """Normalize an Olinda date string to YYYY-MM-DD.

    Olinda returns dates as ISO strings (e.g. '2024-08-15'). Some endpoints
    include a time component ('2024-08-15T00:00:00'). We truncate to the
    date part. Returns '' if the input is empty or unparseable.
    """
    if not d:
        return ""
    s = str(d).strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return ""


def _parse_value(raw) -> float | None:
    """Parse a numeric value from the Olinda response -> float.

    Olinda returns numbers as JSON numbers (already float), but defensive
    parsing handles nulls + string edge cases.
    """
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _parse_int(raw) -> int | None:
    """Parse an integer value from the Olinda response -> int."""
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        try:
            return int(float(raw))
        except (ValueError, TypeError):
            return None


def fetch_expectations(
    indicador: str,
    frequency: str = "monthly",
    top: int = 100,
    force: bool = False,
) -> dict:
    """Fetch the most recent ``top`` expectations for an indicator.

    Args:
        indicador:  'IPCA', 'Selic', 'PIB', 'Cambio'.
        frequency:  'monthly' or 'annual' (determines the Olinda endpoint).
        top:        Maximum number of records to fetch (Olinda $top).
        force:      Bypass cache.

    Returns:
        {"status": "ok", "indicador": <str>, "frequency": <str>, "count": <int>,
         "observations": [{...}, ...], "synced_at": <iso>}

    Each observation has: data, data_referencia, media, mediana, minimo,
    maximo, numero_respondentes, base_calculo.
    """
    cache_key = f"exp:{indicador}:{frequency}:{top}"

    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                return data

    # [v2 fix] Build URL manually — httpx encodes $ as %24 in params, but the
    # BCB Olinda OData API expects literal $filter, $top, $orderby, $format.
    # Using params= causes "types Edm.Boolean and Edm.String not compatible" 400 error.
    base_url = endpoint_url(frequency)
    # URL-encode the filter value (single quotes + spaces) but keep $ literal.
    from urllib.parse import quote as _quote
    filter_val = _quote(f"Indicador eq '{indicador}'", safe="'()")
    query = f"$filter={filter_val}&$orderby=Data desc&$top={top}&$format=json"
    url = f"{base_url}?{query}"
    headers = {"Accept": "application/json"}

    _progress(f"[bcb.focus] Fetching {indicador}/{frequency} (top={top})")

    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, headers=headers, timeout=30,
                             follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "indicador": indicador,
                    "frequency": frequency,
                    "error": f"bcb.focus: {e}"}

    try:
        data = resp.json()
    except ValueError as e:
        return {"status": "error", "indicador": indicador,
                "frequency": frequency,
                "error": f"bcb.focus: invalid JSON - {e}"}

    if not isinstance(data, dict):
        return {"status": "error", "indicador": indicador,
                "frequency": frequency,
                "error": "bcb.focus: unexpected response shape (not a dict)"}

    rows = data.get("value") or []
    if not isinstance(rows, list):
        return {"status": "error", "indicador": indicador,
                "frequency": frequency,
                "error": "bcb.focus: 'value' field is not a list"}

    observations = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        data_ref = _normalize_date(row.get("Data", ""))
        if not data_ref:
            continue  # skip rows with unparseable dates
        obs = {
            "data": data_ref,
            "data_referencia": str(row.get("DataReferencia", "") or ""),
            "media": _parse_value(row.get("Media")),
            "mediana": _parse_value(row.get("Mediana")),
            "minimo": _parse_value(row.get("Minimo")),
            "maximo": _parse_value(row.get("Maximo")),
            "numero_respondentes": _parse_int(row.get("numeroRespondentes")),
            "base_calculo": _parse_int(row.get("baseCalculo")),
        }
        observations.append(obs)

    result = {"status": "ok", "indicador": indicador,
              "frequency": frequency, "count": len(observations),
              "observations": observations, "synced_at": _now_iso()}

    with _cache_lock:
        _cache[cache_key] = (result, time.time())
    return result


def fetch_expectations_concurrent(
    items: list[tuple[str, str]],
    top: int = 100,
    force: bool = False,
) -> dict[tuple[str, str], dict]:
    """Fetch multiple (indicador, frequency) pairs concurrently.

    Args:
        items: list of (indicador, frequency) tuples.
        top:   Maximum records per fetch.
        force: Bypass cache.

    Returns:
        {(indicador, frequency): fetch_result, ...}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[tuple[str, str], dict] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_key = {
            executor.submit(fetch_expectations, ind, freq, top, force): (ind, freq)
            for ind, freq in items
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = {"status": "error", "indicador": key[0],
                                "frequency": key[1], "error": str(e)}
    return results


def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    with _cache_lock:
        _cache.clear()
