"""Browser action: evaluate."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


@register_action(
    "browser",
    "evaluate",
    help_text="""evaluate — Run JavaScript on the page and return the result.
Required: expression
Optional: timeout, headless, trace_id""",
    examples=[
        'browser(action="evaluate", expression="document.title")',
    ],
)
def _action_evaluate(
    expression: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Run JavaScript on the page and return the result."""
    if not expression:
        return fail("expression is required for evaluate action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            result = _run_browser_async(
                page.evaluate(expression), timeout=timeout + 5
            )
        return ok({"result": result, "expression": expression}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Evaluate failed: {e}", trace_id=trace_id)
