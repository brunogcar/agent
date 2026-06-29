"""Browser action: extract_html."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "extract_html",
    help_text="""extract_html — Extract raw HTML from an element or the full page.
Required: none
Optional: selector, timeout, headless, trace_id""",
    examples=[
        'browser(action="extract_html")',
        'browser(action="extract_html", selector="table.data")',
    ],
)
def _action_extract_html(
    selector: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Extract raw HTML from an element or the full page.

    When no selector is provided, returns the full page HTML (<html>...<\\/html>).
    The response labels this as "full_page" to avoid confusion with "body".
    """
    try:
        with _browser_lock:
            page = _run_browser_async(
                _get_page(trace_id, headless), timeout=timeout + 5
            )
            if selector:
                html = _run_browser_async(
                    page.inner_html(selector, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
                selector_label = selector
            else:
                html = _run_browser_async(page.content(), timeout=timeout + 5)
                selector_label = "full_page"
            return ok(
                {"html": html or "", "selector": selector_label},
                trace_id=trace_id,
            )
    except Exception as e:
        return fail(f"extract_html failed: {e}", trace_id=trace_id)
