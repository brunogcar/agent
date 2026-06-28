"""Browser action: extract_links."""
from __future__ import annotations

from core.contracts import fail, ok

from tools.browser_core.factory import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock
from tools.browser_core._registry import register_action


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
    selector: str = "a",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Extract all links from the page or a specific element."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            js = _LINKS_JS.replace("SELECTOR", repr(selector))
            result = _run_browser_async(
                page.evaluate(js), timeout=timeout + 5
            )
        links = result if isinstance(result, list) else []
        return ok({"links": links, "count": len(links)}, trace_id=trace_id)
    except Exception as e:
        return fail(f"extract_links failed: {e}", trace_id=trace_id)
