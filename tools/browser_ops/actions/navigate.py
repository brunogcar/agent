"""Browser action: navigate.

[core/net adoption] Uses get_retry_delay() from core/net/errors.py for unified
backoff (was hardcoded min(2^attempt, 8)). Constants from core/net/default.py.
Keeps hand-rolled retry loop (not retry_sync) because browser retry has special
semantics: same page reuse, Playwright errors aren't in is_retryable_error(),
and retries parameter is caller-controlled.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

from core.contracts import fail, ok
from core.net.security import is_safe_network_address
from core.net.errors import get_retry_delay
from core.net.default import BROWSER_TIMEOUT, BROWSER_NAV_RETRIES, RETRY_BASE_DELAY, RETRY_MAX_DELAY

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "navigate",
    help_text="""navigate — Go to URL and wait for load.
Required: url
Optional: wait_until, timeout, headless, trace_id, retries""",
    examples=[
        'browser(action="navigate", url="https://example.com")',
        'browser(action="navigate", url="https://example.com", wait_until="networkidle")',
        'browser(action="navigate", url="https://example.com", retries=2)',
    ],
)
def _action_navigate(
    url: str = "",
    wait_until: str = "domcontentloaded",
    timeout: int = BROWSER_TIMEOUT,  # [core/net] Was hardcoded 30
    headless: bool = True,
    trace_id: str = "",
    retries: int = BROWSER_NAV_RETRIES,  # [core/net] Was hardcoded 0
    **kwargs,
) -> dict:
    """Navigate to a URL and wait for the page to load.

    Supports retry on transient failures with unified backoff via
    get_retry_delay() from core/net/errors.py.

    NOTE: On retry, the same page/context is reused. If the page crashed
    during the failed attempt, the retry will also fail. A future v2
    improvement may close and recreate the context between retries.

    NOTE: Uses hand-rolled retry loop (not retry_sync) because browser
    retry has special semantics: Playwright errors aren't in
    is_retryable_error(), and the retries parameter is caller-controlled.
    """
    if not url:
        return fail("url is required for navigate action", trace_id=trace_id)

    # Block non-HTTP(S) schemes before any network call.
    # file://, javascript:, data:, etc. are all rejected.
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return fail(
            f"Invalid URL scheme: {url}. Only http:// and https:// are supported.",
            trace_id=trace_id,
        )

    hostname = parsed.hostname or ""
    if not is_safe_network_address(hostname):
        return fail(f"SSRF blocked: {url}", trace_id=trace_id)

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with _browser_lock:
                page = _run_browser_async(
                    _get_page(trace_id, headless), timeout=timeout + 5
                )
                _run_browser_async(
                    page.goto(url, wait_until=wait_until, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
                title = _run_browser_async(page.title(), timeout=10)
                return ok({"url": page.url, "title": title}, trace_id=trace_id)
        except Exception as e:
            last_error = e
            if attempt < retries:
                # [core/net] Unified backoff via get_retry_delay() with jitter.
                # Was: min(2 ** attempt, 8) — hardcoded, no jitter.
                delay = get_retry_delay(attempt, RETRY_BASE_DELAY, RETRY_MAX_DELAY, jitter=True)
                time.sleep(delay)
            continue

    return fail(
        f"Navigation failed after {retries + 1} attempt(s): {last_error}",
        trace_id=trace_id,
    )
