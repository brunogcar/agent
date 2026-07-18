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

    # v1.6: Delegate httpx error classification to core/net/errors.classify_http_error
    # (was: 85-line httpx isinstance ladder + status-code branches that mirrored
    # classify_http_error but didn't call it — explicit "align with classify_http_error"
    # comments in the code but no actual delegation.)
    from core.net.errors import classify_http_error
    error_code = classify_http_error(e)  # returns str, not tuple
    if error_code != "UNKNOWN":
        return fail(
            f"Tavily {error_code.lower()}: {raw_msg}",
            trace_id=trace_id,
            error_code=error_code,
        )

    # Fallback
    return fail(
        f"Tavily error: {raw_msg}",
        trace_id=trace_id,
        error_code="UNKNOWN",
    )
