"""core/net/errors.py — Unified HTTP error classification for all web tools.

Adopted by: tavily_ops, web_ops, browser
v1.1: Extracted from tavily_ops; v1.2: Added BOT_BLOCKED, get_retry_delay,
      is_retryable_error now recognizes Tavily SDK exceptions.
v1.3: Fixed classify_http_error: ReadError/WriteError now return NETWORK_ERROR.
      408 Request Timeout now returns RATE_LIMITED (it's in RETRYABLE_STATUS_CODES).
"""
from __future__ import annotations

import random
from typing import Set, Tuple

import httpx

# ── Retryable Status Codes ──────────────────────────────────────────────────
RETRYABLE_STATUS_CODES: Set[int] = {408, 429, 500, 502, 503, 504}

# ── Retryable Exception Types ────────────────────────────────────────────────
RETRYABLE_EXCEPTIONS: Tuple[type, ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.NetworkError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)

# ── SDK Exception Registry ───────────────────────────────────────────────────
# Tools register their SDK-specific retryable exceptions here.
_RETRYABLE_SDK_EXCEPTIONS: Set[type] = set()


def register_retryable_exception(exc_type: type) -> None:
    """Register an SDK-specific exception type as retryable.

    Usage:
        from tavily.errors import RateLimitError
        from core.net.errors import register_retryable_exception
        register_retryable_exception(RateLimitError)
    """
    _RETRYABLE_SDK_EXCEPTIONS.add(exc_type)


def classify_http_error(e: Exception) -> str:
    """Classify an HTTP-related exception into a canonical category.

    Returns one of:
        TIMEOUT, CONNECT_ERROR, RATE_LIMITED, SERVER_ERROR,
        CLIENT_ERROR, NETWORK_ERROR, BOT_BLOCKED, UNKNOWN
    """
    # Bot / Cloudflare detection (for web_ops scrape)
    if hasattr(e, "response") and e.response is not None:
        try:
            text = getattr(e.response, "text", "") or ""
            if "cloudflare" in text.lower() or "cf-ray" in text.lower():
                return "BOT_BLOCKED"
        except Exception:
            pass

    # Timeout
    if isinstance(e, httpx.TimeoutException):
        return "TIMEOUT"

    # v1.3 FIX: Check ReadError/WriteError/RemoteProtocolError BEFORE NetworkError
    # because they subclass NetworkError in httpx.
    if isinstance(e, (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError)):
        return "NETWORK_ERROR"

    # Connection errors
    if isinstance(e, httpx.ConnectError):
        return "CONNECT_ERROR"

    # Network errors (base class, checked after subclasses)
    if isinstance(e, httpx.NetworkError):
        return "NETWORK_ERROR"

    # HTTP status errors — duck-type status_code for both httpx and SDK wrappers
    status = None
    if hasattr(e, "status_code") and isinstance(e.status_code, int):
        status = e.status_code
    elif hasattr(e, "response") and e.response is not None:
        status = getattr(e.response, "status_code", None)

    if status is not None:
        # v1.3 FIX: 408 is in RETRYABLE_STATUS_CODES, classify as RATE_LIMITED
        if status == 429 or status == 408:
            return "RATE_LIMITED"
        if status >= 500:
            return "SERVER_ERROR"
        if status >= 400:
            return "CLIENT_ERROR"

    return "UNKNOWN"


def is_retryable_error(e: Exception) -> bool:
    """Return True if the error warrants a retry attempt.

    Checks:
      1. HTTP status codes in RETRYABLE_STATUS_CODES
      2. Exception types in RETRYABLE_EXCEPTIONS
      3. Registered SDK-specific exception types
    """
    # Check HTTP status code first
    status = None
    if hasattr(e, "status_code") and isinstance(e.status_code, int):
        status = e.status_code
    elif hasattr(e, "response") and e.response is not None:
        status = getattr(e.response, "status_code", None)

    if status is not None and status in RETRYABLE_STATUS_CODES:
        return True

    # Check exception type
    if isinstance(e, RETRYABLE_EXCEPTIONS):
        return True

    # Check registered SDK exceptions
    if type(e) in _RETRYABLE_SDK_EXCEPTIONS:
        return True

    return False


def get_retry_delay(attempt: int, base_delay: float = 2.0, max_delay: float = 30.0, jitter: bool = True) -> float:
    """Calculate exponential backoff delay with optional jitter.

    Args:
        attempt: Zero-based attempt number (0 = first retry).
        base_delay: Initial delay in seconds.
        max_delay: Cap delay at this value.
        jitter: Add random 0-25% to prevent thundering herd.

    Returns:
        Delay in seconds (float).
    """
    delay = base_delay * (2 ** attempt)
    delay = min(delay, max_delay)
    if jitter:
        delay *= (1.0 + random.random() * 0.25)
    return delay
