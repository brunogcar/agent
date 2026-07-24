"""data_sources/b3/brapi/fetcher.py -- HTTP fetcher for brapi.dev API.

Handles:
  - HTTP GET to brapi.dev with optional token
  - Rate limiting (0.3s between requests — be respectful of free tier)
  - Simple in-memory cache (5min TTL for quotes, 1h for ticker list)

NO local database writes — this module only fetches. sync_engine.py stores.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

import httpx

from data_sources.b3.brapi.catalog import API_BASE

# ── Config ───────────────────────────────────────────────────────────────────

_RATE_LIMIT_SECONDS = 0.3
_CACHE_TTL_QUOTE = 300  # 5 minutes
_CACHE_TTL_TICKERS = 3600  # 1 hour

_cache: dict[str, tuple[object, float]] = {}
_last_request_time: float = 0.0


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

    if not force and cache_key in _cache:
        data, ts = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL_QUOTE:
            return data

    _rate_limit()

    params = {}
    token = _get_token()
    if token:
        params["token"] = token
    if modules:
        params["modules"] = modules

    url = f"{API_BASE}/quote/{ticker}"
    _progress(f"[brapi] Fetching quote: {ticker}")

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

    if not force and cache_key in _cache:
        data, ts = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL_QUOTE:
            return data

    _rate_limit()

    params = {"range": range, "interval": interval}
    token = _get_token()
    if token:
        params["token"] = token

    url = f"{API_BASE}/quote/{ticker}"
    _progress(f"[brapi] Fetching history: {ticker} ({range}/{interval})")

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

    _cache[cache_key] = ({"status": "ok", "ticker": ticker,
                          "count": len(ohlcv), "ohlcv": ohlcv}, time.time())
    return _cache[cache_key][0]


def fetch_tickers(force: bool = False) -> dict:
    """Fetch the full available ticker list (1 call, ~1,796 tickers).

    Replaces the 7,138-page InstrumentsConsolidated sync.
    """
    cache_key = "tickers:all"

    if not force and cache_key in _cache:
        data, ts = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL_TICKERS:
            return data

    _rate_limit()

    params = {}
    token = _get_token()
    if token:
        params["token"] = token

    url = f"{API_BASE}/available"
    _progress("[brapi] Fetching ticker list...")

    try:
        resp = httpx.get(url, params=params, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return {"status": "error", "error": f"brapi.dev: {e}"}

    data = resp.json()
    tickers = data.get("stocks", [])

    result = {"status": "ok", "count": len(tickers), "tickers": tickers}
    _cache[cache_key] = (result, time.time())
    return result


# ── Internal ─────────────────────────────────────────────────────────────────

def _rate_limit():
    """Enforce rate limiting between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.time()


def clear_cache():
    """Clear the in-memory cache."""
    _cache.clear()
