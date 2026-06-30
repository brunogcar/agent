from __future__ import annotations
from typing import Optional
from urllib.parse import urlparse

from core.contracts import fail
from core.config import cfg
from core.security import is_safe_network_address


def _assert_safe_urls(urls: list[str]) -> Optional[str]:
    """Return error string if any URL is unsafe, else None."""
    for url in urls:
        hostname = urlparse(url).hostname or ""
        if not is_safe_network_address(hostname):
            return f"Blocked: {url} resolves to a private/internal address"
    return None


def _handle_tavily_error(e: Exception) -> dict:
    """Map Tavily and network exceptions to standardized fail responses."""
    error_type = type(e).__name__
    error_msg = str(e)

    # Tavily-specific exceptions (imported lazily to avoid hard dependency)
    try:
        from tavily.errors import (
            TavilyAPIError,
            TavilyKeylessLimitError,
            InvalidAPIKeyError,
            UsageLimitExceededError,
        )
    except ImportError:
        TavilyAPIError = TavilyKeylessLimitError = InvalidAPIKeyError = UsageLimitExceededError = None

    is_tavily_keyless = (TavilyKeylessLimitError and isinstance(e, TavilyKeylessLimitError)) or error_type == "TavilyKeylessLimitError"
    is_invalid_key = (InvalidAPIKeyError and isinstance(e, InvalidAPIKeyError)) or error_type == "InvalidAPIKeyError"
    is_usage_limit = (UsageLimitExceededError and isinstance(e, UsageLimitExceededError)) or error_type == "UsageLimitExceededError"
    is_tavily_api = (TavilyAPIError and isinstance(e, TavilyAPIError)) or error_type == "TavilyAPIError"

    if is_tavily_keyless:
        return fail(
            "Tavily keyless rate limit reached. Set TAVILY_API_KEY in .env for higher limits."
        )

    if is_invalid_key:
        return fail(
            "Tavily API key invalid or revoked. Check TAVILY_API_KEY in .env."
        )

    if is_usage_limit:
        return fail("Tavily monthly quota exhausted.")

    if is_tavily_api:
        status = getattr(e, "status_code", 0)
        if status == 429:
            return fail("Tavily rate limit exceeded (HTTP 429). Retry after a short delay.")
        return fail(f"Tavily API error ({status}): {error_msg[:200]}")

    # httpx network errors
    try:
        import httpx
    except ImportError:
        httpx = None

    if httpx:
        if isinstance(e, httpx.TimeoutException):
            return fail(f"Tavily request timed out after {cfg.tavily_timeout}s.")
        if isinstance(e, httpx.ConnectError):
            return fail("Failed to connect to Tavily API. Check network.")
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code if hasattr(e, "response") else 0
            if status == 429:
                return fail("Tavily rate limit exceeded (HTTP 429).")
            if status in (401, 403):
                return fail("Tavily authentication failed. Check API key.")
            return fail(f"Tavily HTTP error {status}: {error_msg[:200]}")

    return fail(f"Tavily error: {error_type}: {error_msg[:200]}")
