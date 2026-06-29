"""Browser action: click."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "click",
    help_text="""click — Click an element by CSS selector.
Required: selector
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="click", selector="button.submit")',
    ],
)
def _action_click(
    selector: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Click an element by CSS selector."""
    if not selector:
        return fail("selector is required for click action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.click(selector, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"clicked": True, "selector": selector}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Click failed: {e}", trace_id=trace_id)
