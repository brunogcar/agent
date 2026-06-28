"""Browser action: wait_for_selector."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "wait_for_selector",
    help_text="""wait_for_selector — Wait for an element to appear in the DOM.
Required: selector
Optional: state, timeout, headless, trace_id""",
    examples=[
        'browser(action="wait_for_selector", selector="div.content")',
        'browser(action="wait_for_selector", selector="div.content", state="visible")',
    ],
)
def _action_wait_for_selector(
    selector: str = "",
    state: str = "visible",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Wait for an element to appear in the DOM."""
    if not selector:
        return fail("selector is required for wait_for_selector action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.wait_for_selector(selector, state=state, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"waited": True, "selector": selector}, trace_id=trace_id)
    except Exception as e:
        return fail(f"wait_for_selector failed: {e}", trace_id=trace_id)
