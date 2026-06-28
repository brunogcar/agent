"""Browser action: type."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "type",
    help_text="""type — Type with human-like delay between keystrokes.
Required: selector, value
Optional: delay, timeout, headless, trace_id""",
    examples=[
        'browser(action="type", selector="input.search", value="hello")',
    ],
)
def _action_type(
    selector: str = "",
    value: str = "",
    delay: int = 50,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Type with human-like delay between keystrokes."""
    if not selector or value is None:
        return fail("selector and value are required for type action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.type(selector, value, delay=delay, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"typed": True, "selector": selector}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Type failed: {e}", trace_id=trace_id)
