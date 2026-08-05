"""data_sources/b3/brapi/fetcher.py -- HTTP fetcher for brapi.dev API.

Handles:
  - HTTP GET to brapi.dev with optional token
  - Thread-safe in-memory cache (5min TTL for quotes, 1h for ticker list)
  - Concurrency limiting via a Semaphore (max 5 in-flight requests)
  - Batch quote fetching via fetch_quotes() using a ThreadPoolExecutor

Thread-safety notes:
  - `_cache` is protected by `_cache_lock` — all reads/writes go through the lock.
  - `_concurrency_semaphore` (max 5) bounds the number of concurrent HTTP requests.
    This replaces the old per-request rate-limit sleep: under concurrent fetch
    (e.g. fetch_quotes()), a Semaphore is simpler and more effective than a
    serialized `time.sleep` gate, which would have defeated parallelism entirely.

NO local database writes — this module only fetches. sync_engine.py stores.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from data_sources.b3.brapi.catalog import API_BASE

# ── Config ───────────────────────────────────────────────────────────────────

_CACHE_TTL_QUOTE = 300  # 5 minutes
_CACHE_TTL_TICKERS = 3600  # 1 hour

_cache: dict[str, tuple[object, float]] = {}

# Thread-safety primitives:
#   _cache_lock             — guards all reads/writes to the _cache dict
#   _concurrency_semaphore  — caps the number of concurrent in-flight HTTP
#                             requests to brapi.dev (brapi free tier is lenient
#                             about total volume but we still want to be nice)
_cache_lock = threading.Lock()
_concurrency_semaphore = threading.Semaphore(5)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _get_token() -> str:
    """Get brapi.dev token from env var (optional — free tier works without)."""
    return os.getenv("BRAPI_TOKEN", "")


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_quote(ticker: str, modules: str = "", force: bool = False) -> dict:
    """Fetch current quote for a ticker.

    Args:
        ticker: B3 ticker (PETR4).
        modules: Optional modules (summaryProfile, financialData, etc.).
        force: Bypass cache.

    Returns:
        Dict with quote data (price, marketCap, PE, etc.) + historicalDataPrice if range requested.
    """
    ticker = ticker.strip().upper()
    cache_key = f"quote:{ticker}:{modules}"

    # Check cache (thread-safe)
    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL_QUOTE:
                return data

    params = {}
    token = _get_token()
    if token:
        params["token"] = token
    if modules:
        params["modules"] = modules

    url = f"{API_BASE}/quote/{ticker}"
    _progress(f"[brapi] Fetching quote: {ticker}")

    # Acquire semaphore (limits concurrency to 5)
    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, params=params, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "error": f"brapi.dev: {e}"}

    data = resp.json()
    results = data.get("results", [])

    if not results:
        return {"status": "not_found", "ticker": ticker,
                "error": f"No data for {ticker}"}

    quote = results[0]

    # Update cache (thread-safe)
    with _cache_lock:
        _cache[cache_key] = (quote, time.time())
    return {"status": "ok", "ticker": ticker, "quote": quote}


def fetch_history(ticker: str, range: str = "1mo", interval: str = "1d",
                  force: bool = False) -> dict:
    """Fetch historical OHLCV for a ticker.

    Args:
        ticker: B3 ticker (PETR4).
        range: Time range (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max).
        interval: Bar interval (1d, 5d, 1wk, 1mo, 3mo).
        force: Bypass cache.

    Returns:
        Dict with OHLCV list.
    """
    ticker = ticker.strip().upper()
    cache_key = f"history:{ticker}:{range}:{interval}"

    # Check cache (thread-safe)
    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL_QUOTE:
                return data

    params = {"range": range, "interval": interval}
    token = _get_token()
    if token:
        params["token"] = token

    url = f"{API_BASE}/quote/{ticker}"
    _progress(f"[brapi] Fetching history: {ticker} ({range}/{interval})")

    # Acquire semaphore (limits concurrency to 5)
    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, params=params, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "error": f"brapi.dev: {e}"}

    data = resp.json()
    results = data.get("results", [])

    if not results:
        return {"status": "not_found", "ticker": ticker,
                "error": f"No data for {ticker}"}

    quote = results[0]
    ohlcv = quote.get("historicalDataPrice", [])

    result = {"status": "ok", "ticker": ticker,
              "count": len(ohlcv), "ohlcv": ohlcv}

    # Update cache (thread-safe)
    with _cache_lock:
        _cache[cache_key] = (result, time.time())
    return result


def fetch_tickers(force: bool = False) -> dict:
    """Fetch the full available ticker list (1 call, ~1,796 tickers).

    Replaces the 7,138-page InstrumentsConsolidated sync.
    """
    cache_key = "tickers:all"

    # Check cache (thread-safe)
    with _cache_lock:
        if not force and cache_key in _cache:
            data, ts = _cache[cache_key]
            if time.time() - ts < _CACHE_TTL_TICKERS:
                return data

    params = {}
    token = _get_token()
    if token:
        params["token"] = token

    url = f"{API_BASE}/available"
    _progress("[brapi] Fetching ticker list...")

    # Acquire semaphore (limits concurrency to 5)
    with _concurrency_semaphore:
        try:
            resp = httpx.get(url, params=params, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"status": "error", "error": f"brapi.dev: {e}"}

    data = resp.json()
    tickers = data.get("stocks", [])

    result = {"status": "ok", "count": len(tickers), "tickers": tickers}

    # Update cache (thread-safe)
    with _cache_lock:
        _cache[cache_key] = (result, time.time())
    return result


def fetch_quotes(tickers: list[str], force: bool = False) -> dict[str, dict]:
    """Fetch quotes for multiple tickers CONCURRENTLY (up to 5 at a time).

    Args:
        tickers: List of B3 tickers (PETR4, VALE3, etc.)
        force: Bypass cache.

    Returns:
        {ticker: quote_result, ...} — one entry per ticker.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {
            executor.submit(fetch_quote, t, "", force): t
            for t in tickers
        }
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                results[ticker] = future.result()
            except Exception as e:
                results[ticker] = {"status": "error", "error": str(e), "ticker": ticker}
    return results


# ── Internal ─────────────────────────────────────────────────────────────────

def clear_cache():
    """Clear the in-memory cache (thread-safe)."""
    with _cache_lock:
        _cache.clear()
