"""core/net/ — Shared network infrastructure for all web-facing tools.

Modules:
- errors: HTTP error classification, retryable detection, backoff calculation
- security: SSRF prevention, URL safety checks, IP validation
- retry: Synchronous and async retry wrappers with circuit breaker hooks
- budget: API cost tracking and budget enforcement
- url: URL normalization and domain extraction
- default: Shared default constants across all network tools

v1.3: Added public re-exports for cross-tool adoption.
"""
from __future__ import annotations

from core.net.errors import (
    RETRYABLE_STATUS_CODES,
    RETRYABLE_EXCEPTIONS,
    classify_http_error,
    is_retryable_error,
    get_retry_delay,
    register_retryable_exception,
)
from core.net.security import (
    is_safe_network_address,
    _assert_safe_urls,
    _is_private_or_localhost,
    _resolve_safe,
)
from core.net.retry import retry_sync, retry_async_factory
from core.net.budget import (
    APICostTracker,
    BudgetConfig,
    record_tool_call,
    check_budget,
    get_budget_status,
    set_tool_budget,
)
from core.net.url import normalize_url, extract_domain, is_same_domain
from core.net.default import (
    SEARCH_MAX_RESULTS,
    SEARCH_TIMEOUT,
    CRAWL_MAX_DEPTH,
    CRAWL_MAX_BREADTH,
    CRAWL_LIMIT,
    EXTRACT_MAX_URLS,
    EXTRACT_DEPTH,
    SCRAPE_TIMEOUT,
    SCRAPE_MAX_RETRIES,
    BROWSER_TIMEOUT,
    BROWSER_NAV_RETRIES,
    RETRY_MAX_ATTEMPTS,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
    RETRY_JITTER,
    CB_FAILURE_THRESHOLD,
    CB_RECOVERY_TIMEOUT,
    CB_HALF_OPEN_MAX_CALLS,
)

__all__ = [
    # errors
    "RETRYABLE_STATUS_CODES",
    "RETRYABLE_EXCEPTIONS",
    "classify_http_error",
    "is_retryable_error",
    "get_retry_delay",
    "register_retryable_exception",
    # security
    "is_safe_network_address",
    "_assert_safe_urls",
    "_is_private_or_localhost",
    "_resolve_safe",
    # retry
    "retry_sync",
    "retry_async_factory",
    # budget
    "APICostTracker",
    "BudgetConfig",
    "record_tool_call",
    "check_budget",
    "get_budget_status",
    "set_tool_budget",
    # url
    "normalize_url",
    "extract_domain",
    "is_same_domain",
    # default
    "SEARCH_MAX_RESULTS",
    "SEARCH_TIMEOUT",
    "CRAWL_MAX_DEPTH",
    "CRAWL_MAX_BREADTH",
    "CRAWL_LIMIT",
    "EXTRACT_MAX_URLS",
    "EXTRACT_DEPTH",
    "SCRAPE_TIMEOUT",
    "SCRAPE_MAX_RETRIES",
    "BROWSER_TIMEOUT",
    "BROWSER_NAV_RETRIES",
    "RETRY_MAX_ATTEMPTS",
    "RETRY_BASE_DELAY",
    "RETRY_MAX_DELAY",
    "RETRY_JITTER",
    "CB_FAILURE_THRESHOLD",
    "CB_RECOVERY_TIMEOUT",
    "CB_HALF_OPEN_MAX_CALLS",
]
