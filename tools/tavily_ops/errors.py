"""tools/tavily_ops/errors.py — Tavily error sanitization + classification.

v1.2: Remove dead TavilyError import, fix API key sanitization, truncate messages.
v1.3: Handle CircuitBreakerOpen, wire budget tracking.
v1.4: Added httpx network error handlers, fixed 408 classification.
"""
from __future__ import annotations

import re

from core.config import cfg
from core.contracts import fail
from core.net.security import _assert_safe_urls as _core_assert_safe_urls
from tools.tavily_ops.bridge import CircuitBreakerOpen


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
    v1.3: Added CircuitBreakerOpen handling.
    v1.4: Added ReadError/WriteError/RemoteProtocolError/NetworkError handlers.
           Fixed 408 mapped to RATE_LIMITED (retryable) instead of CLIENT_ERROR.
    """
    error_type = type(e).__name__
    raw_msg = str(e)

    # v1.3: Handle circuit breaker open first (before sanitization)
    if isinstance(e, CircuitBreakerOpen):
        return fail(
            str(e),
            trace_id=trace_id,
            error_code="CB_OPEN",
        )

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

    # v1.4: Catch remaining httpx network errors (NetworkError is base class;
    # ConnectError above already matched, so these are the non-connect variants)
    if isinstance(e, httpx.NetworkError):
        return fail(
            f"Tavily network error: {raw_msg}",
            trace_id=trace_id,
            error_code="NETWORK_ERROR",
        )

    if isinstance(e, httpx.ReadError):
        return fail(
            f"Tavily read error: {raw_msg}",
            trace_id=trace_id,
            error_code="NETWORK_ERROR",
        )

    if isinstance(e, httpx.WriteError):
        return fail(
            f"Tavily write error: {raw_msg}",
            trace_id=trace_id,
            error_code="NETWORK_ERROR",
        )

    if isinstance(e, httpx.RemoteProtocolError):
        return fail(
            f"Tavily protocol error: {raw_msg}",
            trace_id=trace_id,
            error_code="NETWORK_ERROR",
        )

    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code if e.response else None
        # v1.4: 408 is retryable — align with classify_http_error() in core/net/errors.py
        if status == 429 or status == 408:
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
