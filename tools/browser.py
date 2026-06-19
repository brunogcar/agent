"""tools/browser.py — Browser automation tool (thin @tool facade).

Routes all browser actions to handlers in browser_core/actions.py via the
DISPATCH dict.  This is the only file scanned by registry.py for @tool
decorators; browser_core/ submodules are invisible to the registry.

Phase 3 additions documented in the docstring:
  • wait_for_selector — wait for element to appear
  • scroll            — scroll page or element
  • wait_for_url      — wait for navigation to specific URL

Phase 6 additions:
  • tracer logging on every action dispatch
  • DISPATCH_METADATA for rich "unknown action" error messages
"""
from __future__ import annotations

from core.contracts import fail
from core.tracer import tracer
from registry import tool

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
    direction: str = "",
    amount: int = 0,
) -> dict:
    """Browser automation tool — Playwright-based JS rendering and interaction.

    WHEN TO USE THIS TOOL:
    | Need | Tool | Why |
    |------|------|-----|
    | Static page text | web(read) | Faster, no browser overhead |
    | JS page text | browser(navigate+text_content) | Renders JavaScript |
    | Interactive forms | browser(click, fill, select_option) | Supports interaction |
    | Screenshots | browser(screenshot) | Captures rendered page |
    | Multi-page workflows | browser + sequential actions | Maintains session state |
    | Infinite scroll / lazy load | browser(scroll) | Loads dynamic content |
    | SPA navigation | browser(wait_for_url) | Waits for route change |

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
    return_base64 (optional): Return base64-encoded image (Phase 5)

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

    wait_for_selector: Wait for element to appear in DOM
    selector (required): CSS selector to wait for
    timeout (default: 30): Timeout in seconds

    scroll: Scroll page or element
    selector (optional): CSS selector (default: page body)
    direction (default: "bottom"): "top" | "bottom" | "up" | "down"
    amount (default: 0): Pixels to scroll (0 = full height for top/bottom)

    wait_for_url: Wait for current URL to match pattern
    url (required): URL or glob pattern to wait for
    timeout (default: 30): Timeout in seconds
    """
    action = action.strip().lower()

    # Phase 6: tracer logging for observability
    tracer.step(trace_id, "browser", f"action={action}")

    handler = DISPATCH.get(action)
    if handler is None:
        # Phase 6: rich error message using DISPATCH_METADATA
        valid_actions = " | ".join(DISPATCH.keys())
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
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
        direction=direction,
        amount=amount,
    )
