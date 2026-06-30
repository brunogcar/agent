"""core/web_errors.py — Shared HTTP error classification for web and tavily tools.

Centralizes retry logic, error classification, and backoff constants
to avoid duplication between web_ops and tavily_ops.

v1.1: Created during tavily un-multiplex v1.1 to unify error handling.
web_ops should migrate to use these helpers in a future refactor.
"""
from __future__ import annotations

import httpx

# Retryable status codes (5xx + 429 Too Many Requests)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Retryable exception types
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.NetworkError,
)


def classify_http_error(e: Exception) -> str:
    """Classify an HTTP exception into a canonical error code string.

    Returns one of: TIMEOUT, CONNECT_ERROR, RATE_LIMITED, SERVER_ERROR,
    CLIENT_ERROR, NETWORK_ERROR, UNKNOWN.
    """
    if isinstance(e, httpx.TimeoutException):
        return "TIMEOUT"
    if isinstance(e, httpx.ConnectError):
        return "CONNECT_ERROR"
    if isinstance(e, httpx.NetworkError):
        return "NETWORK_ERROR"
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 429:
            return "RATE_LIMITED"
        if status >= 500:
            return "SERVER_ERROR"
        return "CLIENT_ERROR"
    return "UNKNOWN"


def is_retryable_error(e: Exception) -> bool:
    """Return True if the exception is worth retrying."""
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(e, RETRYABLE_EXCEPTIONS)
