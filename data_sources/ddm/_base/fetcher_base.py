"""data_sources/ddm/_base/fetcher_base.py -- Shared HTTP fetcher infrastructure.

Common building blocks for all 7 DDM fetchers:

  - Three header constants:
      * CLOUDFRONT_HEADERS  -- full Chrome 127 set (used by focus; includes
                               Accept-Encoding).
      * BROWSER_HEADERS     -- Chrome 127 set WITHOUT Accept-Encoding
                               (used by fluxo; CloudFront accepts this
                               variant and it avoids a br/gzip decode path).
      * BOT_HEADERS         -- bare 2-header set (used by acoes, dividends,
                               inflation, juros, poupanca -- endpoints with
                               no CloudFront WAF).
  - BaseDDMFetcher class with the shared HTTP scaffold:
      * _CACHE_TTL = 300 (5 min).
      * _cache / _cache_lock / _concurrency_semaphore (per-subclass via
        __init_subclass__ so each source keeps its own cache namespace
        and its own Semaphore(5) -- preserves the pre-extraction behavior
        where each source could have 5 in-flight requests at once).
      * fetch_page(url, cache_key, headers, slug=None, force=False) classmethod
        implementing the cache-lookup + httpx.get + cache-write pattern.
      * clear_cache() classmethod.
      * _progress / _now_iso / _today_date helpers.

[v2] W4 fix: _today_date() now uses UTC (was local time) for consistency
with _now_iso(). Both are now UTC-based.
[v2] I9 fix: _progress() now uses stdlib logging instead of stderr print.
[v2] I10 fix: Added 0.3s sleep after each fetch for rate limiting.

[Phase 3, Commit 1] Extracted from the 7 fetcher.py files.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import httpx


# [I9] Set up a per-source logger. Each subclass gets its own logger via
# SOURCE_NAME (e.g. "ddm.focus"). Falls back to "ddm" if SOURCE_NAME is empty.
_logger = logging.getLogger("ddm")
if not _logger.handlers:
    # Add a stderr handler if none exists (prevents "No handlers found" warning).
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


# ────────────────────────────────────────────────────────────────────────────
# Header constants
# ────────────────────────────────────────────────────────────────────────────

# Full Chrome 127 header set (focus variant). CloudFront's WAF on the
# /boletim-focus endpoint rejects bare or identifying bot UAs, so we send
# the complete set of browser headers (including Accept-Encoding) to look
# like a real browser.
CLOUDFRONT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Chrome 127 set WITHOUT Accept-Encoding (fluxo variant). The /fluxo
# endpoint is also CloudFront-protected but accepts this slightly leaner
# header set. Avoiding Accept-Encoding skips the gzip/br decode path,
# which keeps the response handling identical to the bare-UA fetchers.
BROWSER_HEADERS = {
    "User-Agent": CLOUDFRONT_HEADERS["User-Agent"],
    "Accept": CLOUDFRONT_HEADERS["Accept"],
    "Accept-Language": CLOUDFRONT_HEADERS["Accept-Language"],
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Bare 2-header set (acoes, dividends, inflation, juros, poupanca). These
# endpoints have no CloudFront WAF and accept a minimal identifying
# User-Agent. The "compatible; ddm-fetcher/1.0" suffix lets the upstream
# identify scraper traffic in their logs (polite bot disclosure).
BOT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": "Mozilla/5.0 (compatible; ddm-fetcher/1.0)",
}


# ────────────────────────────────────────────────────────────────────────────
# BaseDDMFetcher
# ────────────────────────────────────────────────────────────────────────────

class BaseDDMFetcher:
    """Base class for DDM HTTP fetchers.

    Subclasses set:
        SOURCE_NAME: str  -- e.g. "inflation" (used in log prefix
                             "[ddm.inflation]" and error message
                             "ddm.inflation: {e}").

    Provides:
        fetch_page(url, cache_key, headers, slug=None, force=False)
            -- the cache-lookup + httpx.get + cache-write pattern that's
               identical across all 7 fetchers. When `slug` is provided
               (multi-page sources), the result dict includes a "slug" key
               and the error dict includes a "slug" key. When `slug` is
               None (single-page sources), neither dict has a "slug" key.
        clear_cache()
        _progress(msg), _now_iso(), _today_date()

    Subclass instantiation:
        __init_subclass__ gives each subclass its OWN _cache dict, _cache_lock,
        and _concurrency_semaphore (Semaphore(5)). This preserves the
        pre-extraction behavior where each source had independent cache
        state and its own 5-concurrent-request cap.
    """

    SOURCE_NAME: str = ""
    _CACHE_TTL: int = 300

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Each subclass gets its own cache + lock + semaphore so source
        # caches don't share state and each source can have 5 in-flight
        # requests (matching the pre-extraction behavior).
        cls._cache: dict[str, tuple[object, float]] = {}
        cls._cache_lock = threading.Lock()
        cls._concurrency_semaphore = threading.Semaphore(5)
        # [I9] Per-subclass logger.
        cls._logger = logging.getLogger(f"ddm.{cls.SOURCE_NAME}") if cls.SOURCE_NAME else _logger

    @classmethod
    def _progress(cls, msg: str) -> None:
        """[I9] Log via stdlib logging instead of stderr print."""
        cls._logger.info(msg)

    @classmethod
    def _now_iso(cls) -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _today_date(cls) -> str:
        """[W4] Return today's date as YYYY-MM-DD (UTC).

        Previously used local time, which was inconsistent with _now_iso()
        (UTC). At 23:30 BRT (02:30 UTC), this created a ref_date vs
        synced_at mismatch. Now both use UTC.
        """
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @classmethod
    def fetch_page(
        cls,
        url: str,
        cache_key: str,
        headers: dict,
        slug: str | None = None,
        force: bool = False,
    ) -> dict:
        """Fetch a DDM HTML page with 5-min cache + concurrency cap.

        Args:
            url:        Full URL to fetch.
            cache_key:  Cache key (e.g. "page:acoes" or f"page:{slug}").
            headers:    Headers dict (one of CLOUDFRONT_HEADERS /
                        BROWSER_HEADERS / BOT_HEADERS, or a custom dict).
            slug:       Optional slug (multi-page sources). When provided,
                        the result dict includes a "slug" key.
            force:      Bypass cache.

        Returns:
            {"status": "ok", "html": <str>, "synced_at": <iso>}
            -- single-page (slug=None)
            {"status": "ok", "slug": <str>, "html": <str>, "synced_at": <iso>}
            -- multi-page (slug=<str>)
            {"status": "error", "error": "ddm.<src>: {e}"}
            -- single-page error
            {"status": "error", "slug": <str>, "error": "ddm.<src>: {e}"}
            -- multi-page error

        [I10] Added 0.3s sleep after each fetch for rate limiting (politeness
        to dadosdemercado.com.br).
        """
        with cls._cache_lock:
            if not force and cache_key in cls._cache:
                data, ts = cls._cache[cache_key]
                if time.time() - ts < cls._CACHE_TTL:
                    return data

        src = cls.SOURCE_NAME
        log_prefix = f"[ddm.{src}]"
        if slug:
            log_prefix = f"{log_prefix} Fetching index page {slug} ({url})"
        else:
            log_prefix = f"{log_prefix} Fetching {src} page ({url})"
        cls._progress(log_prefix)

        with cls._concurrency_semaphore:
            try:
                resp = httpx.get(
                    url, headers=headers, timeout=30, follow_redirects=True,
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                err = f"ddm.{src}: {e}"
                if slug is not None:
                    return {"status": "error", "slug": slug, "error": err}
                return {"status": "error", "error": err}
            # [I10] Rate limiting: 0.3s sleep after each successful fetch.
            # Politeness to dadosdemercado.com.br — prevents burst when
            # 5 concurrent threads finish simultaneously.
            time.sleep(0.3)

        html = resp.text
        result: dict = {
            "status":    "ok",
            "html":      html,
            "synced_at": cls._now_iso(),
        }
        if slug is not None:
            # Insert slug as the 2nd key to match the pre-extraction shape
            # {"status", "slug", "html", "synced_at"}.
            result = {
                "status":    "ok",
                "slug":      slug,
                "html":      html,
                "synced_at": result["synced_at"],
            }

        with cls._cache_lock:
            cls._cache[cache_key] = (result, time.time())
        return result

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the in-memory cache (thread-safe)."""
        with cls._cache_lock:
            cls._cache.clear()
