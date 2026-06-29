"""Browser action: extract_links."""
from __future__ import annotations

import json

from core.contracts import fail, ok

from tools.browser_ops.factory import _get_page
from tools.browser_ops.loop import _run_browser_async
from tools.browser_ops.state import _browser_lock
from tools.browser_ops._registry import register_action


# Playwright page.evaluate() accepts a JS function string + arguments.
# We inject the selector via json.dumps() (not repr()) to ensure valid JS
# string literals even for Unicode astral characters and quote-containing
# selectors. The SELECTOR placeholder is replaced at runtime.
_LINKS_JS = """
(() => {
    const links = Array.from(document.querySelectorAll(SELECTOR));
    return links.map(a => ({
        href: a.href,
        text: a.textContent.trim(),
        title: a.title || ""
    })).filter(a => a.href);
})()
"""


@register_action(
    "browser",
    "extract_links",
    help_text="""extract_links — Extract all links from the page or a specific element.
Required: none
Optional: selector, timeout, headless, trace_id""",
    examples=[
        'browser(action="extract_links")',
        'browser(action="extract_links", selector="nav a")',
    ],
)
def _action_extract_links(
    selector: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Extract all links from the page or a specific element.

    When selector is empty, defaults to "a" (all anchor tags).
    Uses json.dumps() to safely embed the selector into the JS string,
    preventing injection of malformed selectors.
    """
    try:
        with _browser_lock:
            page = _run_browser_async(
                _get_page(trace_id, headless), timeout=timeout + 5
            )
            # Default to "a" when selector is empty (facade passes "" by default).
            effective_selector = selector or "a"
            js = _LINKS_JS.replace("SELECTOR", json.dumps(effective_selector))
            result = _run_browser_async(
                page.evaluate(js), timeout=timeout + 5
            )
            links = result if isinstance(result, list) else []
            return ok({"links": links, "count": len(links)}, trace_id=trace_id)
    except Exception as e:
        return fail(f"extract_links failed: {e}", trace_id=trace_id)
