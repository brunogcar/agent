"""tools/browser.py — Playwright-based browser automation.
Global singleton browser with trace-scoped contexts for isolation.

Thin @tool facade. All logic lives in browser_core/ submodules.

Actions:
 navigate, click, fill, type, screenshot, text_content, evaluate,
 select_option, keyboard_press, get_url, close, wait_for_selector

NOT_PARALLEL_SAFE: Browser is stateful and heavy. All calls are serialized
via a module-level threading.Lock().

See docs/BROWSER.md for full documentation.
"""
from __future__ import annotations

from registry import tool
from core.contracts import fail
from core.tracer import tracer
from tools.browser_core.actions import DISPATCH, DISPATCH_METADATA

# Module-level flags
PARALLEL_SAFE = False


@tool
def browser(
    action: str,
    url: str = "",
    selector: str = "",
    value: str = "",
    path: str = "",
    wait_until: str = "domcontentloaded",
    timeout: int = 30,
    delay: int = 50,
    key: str = "",
    expression: str = "",
    headless: bool = True,
    return_base64: bool = False,
    trace_id: str = "",
) -> dict:
    """
    Browser automation tool — Playwright-based JS rendering and interaction.

    WHEN TO USE THIS TOOL:
    | Need | Tool | Why |
    |------|------|-----|
    | Static page text | web(read) | Faster, no browser overhead |
    | JS page text | browser(navigate+text_content) | Renders JavaScript |
    | Interactive forms | browser(click, fill, select_option) | Supports interaction |
    | Screenshots | browser(screenshot) | Captures rendered page |
    | Multi-page workflows | browser + sequential actions | Maintains session state |

    STATE MANAGEMENT:
    - Browser is a global singleton (launched once, reused).
    - Each workflow trace gets its own BrowserContext (isolated cookies).
    - State persists within a trace but is isolated between traces.
    - Use action="close" to explicitly clean up.

    SCREENSHOT CLEANUP:
    - Screenshots older than 7 days are auto-deleted on startup and every 6 hours.
    - Use action="screenshot" with explicit path= to keep important shots.

    ACTIONS:
    navigate: Go to URL and wait for load
    url (required): URL to navigate to
    wait_until (default: "domcontentloaded"): "networkidle", "domcontentloaded", "load"
    timeout (default: 30): Timeout in seconds

    click: Click an element
    selector (required): CSS selector (e.g., "button.submit")
    timeout (default: 30): Timeout in seconds

    fill: Clear and type into an input
    selector (required): CSS selector
    value (required): Text to type
    timeout (default: 30): Timeout in seconds

    type: Type with human-like delay
    selector (required): CSS selector
    value (required): Text to type
    delay (default: 50): Delay between keystrokes (ms)

    screenshot: Capture page or element
    selector (optional): CSS selector (default: full page)
    path (optional): Save path (default: workspace/screenshots/{trace_id}_{timestamp}.png)

    text_content: Extract text from element
    selector (required): CSS selector (default: "body")

    evaluate: Run JavaScript
    expression (required): JS code to execute (e.g., "document.title")

    select_option: Select dropdown option
    selector (required): CSS selector for <select>
    value (required): Option value to select

    keyboard_press: Press a key
    key (required): Key name (Enter, Tab, Escape, etc.)

    get_url: Return current page URL

    close: Close browser context for this trace

    wait_for_selector: Wait until element appears in DOM
    selector (required): CSS selector
    timeout (default: 30): Max wait time in seconds
    """
    action = action.strip().lower()

    tracer.step(trace_id, "browser", f"action={action}")

    handler = DISPATCH.get(action)
    if handler is None:
        known = ", ".join(DISPATCH.keys())
        return fail(
            f"Unknown action '{action}'. Use: {known}",
            trace_id=trace_id,
        )

    return handler(
        url=url,
        selector=selector,
        value=value,
        path=path,
        wait_until=wait_until,
        timeout=timeout,
        delay=delay,
        key=key,
        expression=expression,
        headless=headless,
        return_base64=return_base64,
        trace_id=trace_id,
    )
