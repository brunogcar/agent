"""Browser action: select_option."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "select_option",
    help_text="""select_option — Select an option from a <select> dropdown.
Required: selector, value
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="select_option", selector="select.country", value="US")',
    ],
)
def _action_select_option(
    selector: str = "",
    value: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Select an option from a <select> dropdown by its value attribute."""
    if not selector or value is None:
        return fail(
            "selector and value are required for select_option action",
            trace_id=trace_id,
        )
    try:
        with _browser_lock:
            page = _run_browser_async(
                _get_page(trace_id, headless), timeout=timeout + 5
            )
            _run_browser_async(
                page.select_option(selector, value, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
            return ok({"selected": value, "selector": selector}, trace_id=trace_id)
    except Exception as e:
        return fail(f"select_option failed: {e}", trace_id=trace_id)
