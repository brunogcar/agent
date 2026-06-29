"""Browser action: text_content."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


@register_action(
    "browser",
    "text_content",
    help_text="""text_content — Extract text from an element (default: body).
Required: none
Optional: selector, timeout, headless, trace_id""",
    examples=[
        'browser(action="text_content")',
        'browser(action="text_content", selector="h1")',
    ],
)
def _action_text_content(
    selector: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Extract text from an element (default: body)."""
    target_selector = selector or "body"
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            text = _run_browser_async(
                page.text_content(target_selector, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"text": text or "", "selector": target_selector}, trace_id=trace_id)
    except Exception as e:
        return fail(f"text_content failed: {e}", trace_id=trace_id)
