"""Browser action: extract_html."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


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
    """Extract raw HTML from an element or the full page."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            if selector:
                html = _run_browser_async(
                    page.inner_html(selector, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
            else:
                html = _run_browser_async(page.content(), timeout=timeout + 5)
        return ok({"html": html or "", "selector": selector or "body"}, trace_id=trace_id)
    except Exception as e:
        return fail(f"extract_html failed: {e}", trace_id=trace_id)
