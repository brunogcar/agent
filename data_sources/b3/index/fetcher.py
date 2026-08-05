"""data_sources/b3/index/fetcher.py -- HTTP fetcher for B3 indexProxy API.

Handles:
  - Base64 URL construction (payload encoded in URL path)
  - Anti-WAF headers (User-Agent + Referer)
  - Thread-safe concurrency (Semaphore(5))
  - In-memory cache (1h TTL - indices update quarterly)

NO local database writes. sync_engine.py stores.
"""
from __future__ import annotations

import base64
import json
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from data_sources.b3.index.catalog import API_BASE

_CACHE_TTL = 3600  # 1 hour (indices update quarterly)
_MAX_CONCURRENT = 5

_cache: dict[str, tuple[object, float]] = {}
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(_MAX_CONCURRENT)

_WAF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sistemaswebb3-listados.b3.com.br/",
}


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_date(dmy: str) -> str:
    """Convert MM/DD/YY -> YYYY-MM-DD (B3 returns dates as MM/DD/YY)."""
    if not dmy:
        return ""
    try:
        parts = dmy.split("/")
        if len(parts) == 3:
            mo, dy, yr = parts
            if len(yr) == 2:
                yr = "20" + yr
            return f"{yr}-{mo.zfill(2)}-{dy.zfill(2)}"
    except Exception:
        pass
    return ""


def _parse_int(raw) -> int | None:
    """Parse B3 theoricalQty (comma-separated thousands) -> int."""
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_float(raw) -> float | None:
    """Parse B3 participation (dot decimal) -> float."""
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw))
    except (ValueError, TypeError):
        return None


def fetch_index(index_code: str, force: bool = False) -> dict:
    """Fetch current index composition from B3 indexProxy.

    Args:
        index_code: B3 index code (IBOV, SMLL, BDRX, IFIX, IDIV).
        force: Bypass cache.

    Returns:
        {"status": "ok", "index": <code>, "ref_date": "YYYY-MM-DD",
         "constituents": [{ticker, company_name, type, theorical_qty, participation}, ...]}
    """
    cache_key = f"index:{index_code}"

    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                return data

    payload = json.dumps({
        "language": "en-us",
        "pageNumber": 1,
        "pageSize": 200,
        "index": index_code,
        "segment": "1",
    })
    b64 = base64.b64encode(payload.encode()).decode()
    url = f"{API_BASE}/{b64}"

    _progress(f"[b3.index] Fetching {index_code}")

    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, headers=_WAF_HEADERS, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "index": index_code, "error": f"b3.index: {e}"}

    try:
        data = resp.json()
    except ValueError as e:
        return {"status": "error", "index": index_code, "error": f"b3.index: invalid JSON - {e}"}

    if not isinstance(data, dict) or "results" not in data:
        return {"status": "not_found", "index": index_code,
                "error": f"No data for index {index_code}"}

    ref_date = _normalize_date(data.get("header", {}).get("date", ""))
    results = data.get("results", [])

    constituents = []
    for r in results:
        ticker = (r.get("cod") or "").strip()
        if not ticker or ticker == "Redutor":
            continue
        constituents.append({
            "ticker": ticker,
            "company_name": (r.get("asset") or "").strip(),
            "type": (r.get("type") or "").strip(),
            "theorical_qty": _parse_int(r.get("theoricalQty")),
            "participation": _parse_float(r.get("part")),
        })

    # Rank by participation (descending)
    constituents.sort(key=lambda c: c.get("participation") or 0, reverse=True)
    for i, c in enumerate(constituents, 1):
        c["rank"] = i

    result = {
        "status": "ok",
        "index": index_code,
        "ref_date": ref_date,
        "constituent_count": len(constituents),
        "constituents": constituents,
        "synced_at": _now_iso(),
    }

    with _cache_lock:
        _cache[cache_key] = (result, time.time())

    return result


def fetch_indices_concurrent(index_codes: list[str],
                             force: bool = False) -> dict[str, dict]:
    """Fetch multiple indices concurrently (up to 5 at a time)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT) as executor:
        future_to_code = {
            executor.submit(fetch_index, code, force): code
            for code in index_codes
        }
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                results[code] = future.result()
            except Exception as e:
                results[code] = {"status": "error", "index": code, "error": str(e)}
    return results


def clear_cache():
    with _cache_lock:
        _cache.clear()
