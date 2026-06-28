"""Browser action: get_url."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "get_url",
    help_text="""get_url — Return the current page URL.
Required: none
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="get_url")',
    ],
)
def _action_get_url(
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Return the current page URL."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            current_url = page.url
        return ok({"url": current_url}, trace_id=trace_id)
    except Exception as e:
        return fail(f"get_url failed: {e}", trace_id=trace_id)
