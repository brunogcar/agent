"""Browser action: hover."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "hover",
    help_text="""hover — Hover over an element. Triggers CSS :hover states and dropdowns.
Required: selector
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="hover", selector=".menu-item")',
    ],
)
def _action_hover(
    selector: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Hover over an element. Triggers CSS :hover states and dropdowns."""
    if not selector:
        return fail("selector is required for hover action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.hover(selector, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"hovered": True, "selector": selector}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Hover failed: {e}", trace_id=trace_id)
