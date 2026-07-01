"""tools/tavily_ops/errors.py — Tavily error sanitization + classification.

v1.2 FIXES:
- Remove dead TavilyError import.
- Fix API key sanitization (regex + length guard + URL patterns).
- Truncate error messages to 500 chars to prevent token waste.
- Use core/net/errors for HTTP classification.
"""
from __future__ import annotations

import re

from core.config import cfg
from core.contracts import fail
from core.net.security import _assert_safe_urls as _core_assert_safe_urls


def _assert_safe_urls(urls):
    """Wrapper: delegate to core.net.security._assert_safe_urls.

    Maintains backward-compatible string return for action handlers.
    v1.2: Direct import from core.net.security (no lazy import needed).
    """
    safe, err = _core_assert_safe_urls(urls)
    return err if not safe else ""


def _handle_tavily_error(e, trace_id=""):
    """Classify and sanitize a Tavily exception into a fail() dict.

    v1.2: Enhanced API key sanitization, error truncation, structured error_code.
    """
    error_type = type(e).__name__
    raw_msg = str(e)

    # ── API Key Sanitization ────────────────────────────────────────────────
    api_key = getattr(cfg, "tavily_api_key", None)
    if api_key and len(api_key) > 4:
        # Replace exact key and URL-encoded variants
        escaped_key = re.escape(api_key)
        raw_msg = re.sub(escaped_key, "***", raw_msg)
        # URL-encoded variant
        raw_msg = re.sub(re.escape(api_key.replace("-", "%2D")), "***", raw_msg)
        # Strip Authorization header patterns
        raw_msg = re.sub(r"Authorization:\s*Bearer\s+[^\s]+", "Authorization: Bearer ***", raw_msg)
        # Strip query param patterns
        raw_msg = re.sub(r"[?&]api_key=[^&\s]+", "api_key=***", raw_msg)

    # Truncate to prevent token waste in LLM context
    raw_msg = raw_msg[:500]

    # ── Classification ───────────────────────────────────────────────────────
    if error_type == "TavilyKeylessLimitError":
        return fail(
            "Tavily keyless rate limit reached. Set TAVILY_API_KEY in .env for full access.",
            trace_id=trace_id,
            error_code="AUTH_FAILED",
        )

    if error_type == "InvalidAPIKeyError":
        return fail(
            "Tavily API key is invalid. Check TAVILY_API_KEY in .env.",
            trace_id=trace_id,
            error_code="AUTH_FAILED",
        )

    if error_type == "UsageLimitExceededError":
        return fail(
            "Tavily monthly quota exhausted. Upgrade your plan or wait for reset.",
            trace_id=trace_id,
            error_code="QUOTA_EXHAUSTED",
        )

    # Tavily SDK RateLimitError
    if error_type == "RateLimitError":
        return fail(
            f"Tavily rate limit: {raw_msg}",
            trace_id=trace_id,
            error_code="RATE_LIMITED",
        )

    # Tavily SDK APIError — check status code
    if error_type == "APIError":
        status = getattr(e, "status_code", None)
        if status == 429:
            return fail(
                f"Tavily rate limit (HTTP {status}): {raw_msg}",
                trace_id=trace_id,
                error_code="RATE_LIMITED",
            )
        if status and status >= 500:
            return fail(
                f"Tavily server error (HTTP {status}): {raw_msg}",
                trace_id=trace_id,
                error_code="SERVER_ERROR",
            )
        return fail(
            f"Tavily API error: {raw_msg}",
            trace_id=trace_id,
            error_code="API_ERROR",
        )

    # httpx exceptions
    import httpx
    if isinstance(e, httpx.TimeoutException):
        return fail(
            f"Tavily request timed out: {raw_msg}",
            trace_id=trace_id,
            error_code="TIMEOUT",
        )

    if isinstance(e, httpx.ConnectError):
        return fail(
            f"Tavily connection failed: {raw_msg}",
            trace_id=trace_id,
            error_code="CONNECT_ERROR",
        )

    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code if e.response else None
        if status == 429:
            return fail(
                f"Tavily rate limit (HTTP 429): {raw_msg}",
                trace_id=trace_id,
                error_code="RATE_LIMITED",
            )
        if status and status >= 500:
            return fail(
                f"Tavily server error (HTTP {status}): {raw_msg}",
                trace_id=trace_id,
                error_code="SERVER_ERROR",
            )
        return fail(
            f"Tavily HTTP error (HTTP {status}): {raw_msg}",
            trace_id=trace_id,
            error_code="CLIENT_ERROR",
        )

    # Fallback
    return fail(
        f"Tavily error: {raw_msg}",
        trace_id=trace_id,
        error_code="UNKNOWN",
    )
