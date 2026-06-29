"""Browser action: scroll."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "scroll",
    help_text="""scroll — Scroll the page or a specific element.
Required: none
Optional: selector, direction, amount, timeout, headless, trace_id""",
    examples=[
        'browser(action="scroll", direction="bottom")',
        'browser(action="scroll", selector="#target")',
        'browser(action="scroll", direction="down", amount=500)',
    ],
)
def _action_scroll(
    selector: str = "",
    direction: str = "bottom",
    amount: int = 0,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Scroll the page or a specific element."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)

            if selector:
                element = _run_browser_async(
                    page.query_selector(selector), timeout=timeout + 5
                )
                if not element:
                    return fail(f"Element not found: {selector}", trace_id=trace_id)
                _run_browser_async(
                    element.scroll_into_view_if_needed(), timeout=timeout + 5
                )
                return ok({"scrolled": True, "selector": selector}, trace_id=trace_id)

            js_map = {
                "top": "window.scrollTo(0, 0)",
                "bottom": "window.scrollTo(0, document.body.scrollHeight)",
                "up": f"window.scrollBy(0, -{amount or 1000})",
                "down": f"window.scrollBy(0, {amount or 1000})",
            }
            js = js_map.get(direction, js_map["bottom"])
            _run_browser_async(page.evaluate(js), timeout=timeout + 5)

        return ok({"scrolled": True, "direction": direction, "amount": amount}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Scroll failed: {e}", trace_id=trace_id)
