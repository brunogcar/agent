"""Browser action: wait_for_url."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "wait_for_url",
    help_text="""wait_for_url — Wait for current URL to match a pattern.
Required: url
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="wait_for_url", url="**/dashboard")',
    ],
)
def _action_wait_for_url(
    url: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Wait for the current page URL to match a pattern."""
    if not url:
        return fail("url is required for wait_for_url action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.wait_for_url(url, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"waited": True, "url": page.url}, trace_id=trace_id)
    except Exception as e:
        return fail(f"wait_for_url failed: {e}", trace_id=trace_id)
