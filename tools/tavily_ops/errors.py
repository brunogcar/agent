"""tools/tavily_ops/errors.py — Tavily error handling and SSRF guards.

v1.1: _assert_safe_urls has been moved to core.security for cross-tool sharing.
This module re-exports it for backward compatibility with action files.
API key sanitization added to prevent accidental key leakage in error messages.
"""
from __future__ import annotations

from core.config import cfg
from core.contracts import fail

# v1.1: Import shared SSRF guard from core.security.
# Re-export is_safe_network_address for backward compatibility — existing tests
# patch tools.tavily_ops.errors.is_safe_network_address and action files
# import from here.
from core.security import is_safe_network_address


def _assert_safe_urls(urls):
    """Block private/internal URLs before sending to any external API.

    v1.1: Delegates to core.security._assert_safe_urls (tuple API) and
    converts back to the original string-return API for backward
    compatibility with existing action file callers.

    Returns:
        Empty string "" if all URLs are safe.
        Error message string if any URL is blocked.
    """
    from core.security import _assert_safe_urls as _core_assert
    safe, err = _core_assert(urls)
    return err if not safe else ""


def _handle_tavily_error(e, trace_id=""):
    """Convert a Tavily SDK or httpx exception into a clean fail() dict.

    v1.1: Added API key sanitization — strips the Tavily API key from error
    messages before returning to the LLM, preventing accidental leakage into
    logs or context windows.
    """
    # Lazy import fallback strategy: if tavily-python isn't installed,
    # we still produce a clean error dict without crashing on import.
    try:
        from tavily import TavilyError
        # v1.1 FIX: Added TavilyKeylessLimitError to the import.
        from tavily.errors import APIError, RateLimitError, TavilyKeylessLimitError
        import httpx
    except ImportError:
        TavilyError = APIError = RateLimitError = TavilyKeylessLimitError = None
        httpx = None

    # v1.1: Sanitize API key from error messages before returning to LLM.
    raw_msg = str(e)
    api_key = cfg.tavily_api_key
    if api_key and api_key in raw_msg:
        raw_msg = raw_msg.replace(api_key, "***")

    # Determine if this is a keyless-limit error (free tier exhausted)
    error_type = type(e).__name__
    is_tavily_keyless = (
        (TavilyKeylessLimitError and isinstance(e, TavilyKeylessLimitError))
        or error_type == "TavilyKeylessLimitError"
    )

    if is_tavily_keyless:
        return fail(
            "Tavily keyless rate limit reached. Set TAVILY_API_KEY in .env for full access.",
            trace_id=trace_id,
        )

    if RateLimitError and isinstance(e, RateLimitError):
        return fail(
            "Tavily rate limit exceeded. Please wait a moment and retry.",
            trace_id=trace_id,
        )

    # v1.1: Handle specific SDK error types that tests expect.
    if error_type == "InvalidAPIKeyError":
        return fail(
            "Tavily API key invalid. Check TAVILY_API_KEY in .env.",
            trace_id=trace_id,
        )
    if error_type == "UsageLimitExceededError":
        return fail(
            "Tavily quota exhausted. Upgrade your plan or wait for reset.",
            trace_id=trace_id,
        )

    if APIError and isinstance(e, APIError):
        status = getattr(e, "status_code", None)
        if status == 429:
            return fail(
                "Tavily rate limit exceeded (429). Please wait a moment and retry.",
                trace_id=trace_id,
            )
        if status == 401:
            return fail(
                "Tavily authentication failed (401). Check your API key.",
                trace_id=trace_id,
            )
        if status == 403:
            return fail(
                "Tavily access denied (403). Check your API key or plan.",
                trace_id=trace_id,
            )
        return fail(
            f"Tavily API error: {raw_msg}",
            trace_id=trace_id,
        )

    if httpx and isinstance(e, httpx.TimeoutException):
        return fail(
            f"Tavily request timed out after {cfg.tavily_timeout}s.",
            trace_id=trace_id,
        )

    if httpx and isinstance(e, httpx.ConnectError):
        return fail(
            "Cannot connect to Tavily API. Check your network or API endpoint.",
            trace_id=trace_id,
        )

    # v1.1: Handle httpx.HTTPStatusError with status-specific messages.
    if httpx and isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 429:
            return fail(
                "Tavily rate limit exceeded (429). Please wait a moment and retry.",
                trace_id=trace_id,
            )
        if status == 401:
            return fail(
                "Tavily authentication failed (401). Check your API key.",
                trace_id=trace_id,
            )
        if status == 403:
            return fail(
                "Tavily access denied (403). Check your API key or plan.",
                trace_id=trace_id,
            )
        return fail(
            f"Tavily HTTP error {status}: {raw_msg}",
            trace_id=trace_id,
        )

    # Fallback for any other exception
    return fail(
        f"Tavily error: {raw_msg}",
        trace_id=trace_id,
    )
