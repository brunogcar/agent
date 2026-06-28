"""Browser action: navigate."""
from __future__ import annotations

from urllib.parse import urlparse

from core.contracts import fail, ok
from core.security import is_safe_network_address

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "navigate",
    help_text="""navigate — Go to URL and wait for load.
Required: url
Optional: wait_until, timeout, headless, trace_id""",
    examples=[
        'browser(action="navigate", url="https://example.com")',
        'browser(action="navigate", url="https://example.com", wait_until="networkidle")',
    ],
)
def _action_navigate(
    url: str = "",
    wait_until: str = "domcontentloaded",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Navigate to a URL and wait for the page to load."""
    if not url:
        return fail("url is required for navigate action", trace_id=trace_id)
    hostname = urlparse(url).hostname or ""
    if not is_safe_network_address(hostname):
        return fail(f"SSRF blocked: {url}", trace_id=trace_id)

    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.goto(url, wait_until=wait_until, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
            title = _run_browser_async(page.title(), timeout=10)
        return ok({"url": page.url, "title": title}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Navigation failed: {e}", trace_id=trace_id)
