"""tools/browser.py — Browser automation tool (thin @tool facade).

Routes all browser actions to handlers in browser_core/actions/ via the
DISPATCH dict. This is the only file scanned by registry.py for @tool
decorators; browser_core/ submodules are invisible to the registry.

Phase 3 additions: wait_for_selector, scroll, wait_for_url
Phase 6 additions: tracer logging, DISPATCH_METADATA (replaced by @meta_tool)
Post-refactor additions: hover, cookies, set_viewport, extract_html,
    screenshot base64, screenshot-on-failure, tracer spans
V1.1 additions: navigate retry, upload action, cookies URL filter,
    close trace_id enforcement, extract_links/extract_tables safety fixes
"""
from __future__ import annotations

import time
from pathlib import Path

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

from tools.browser_core._registry import DISPATCH

# Module-level flags
PARALLEL_SAFE = False


def _try_failure_screenshot(trace_id: str) -> str | None:
    """Best-effort screenshot on failure. Returns path or None.

    Lazy-imports cfg to avoid creating an unpatched module-level binding
    that breaks tests (conftest patches tools.browser_core.actions.screenshot.cfg
    but not tools.browser.cfg).
    """
    try:
        from core.config import cfg  # lazy — only needed on failure path
        from tools.browser_core.factory import _get_page
        from tools.browser_core.loop import _run_browser_async
        from tools.browser_core.state import _browser_lock

        err_path = (
            cfg.workspace_root
            / "screenshots"
            / f"error_{trace_id}_{int(time.time())}.png"
        )
        err_path.parent.mkdir(parents=True, exist_ok=True)
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, True), timeout=10)
            _run_browser_async(
                page.screenshot(path=str(err_path), full_page=True), timeout=10
            )
        return str(err_path)
    except Exception:
        return None


@tool
@meta_tool(
    DISPATCH.get("browser", {}),
    doc_sections=[
        "WHEN TO USE THIS TOOL:",
        " | Need | Tool | Why |",
        " |------|------|-----|",
        " | Static page text | web(read) | Faster, no browser overhead |",
        " | JS page text | browser(navigate+text_content) | Renders JavaScript |",
        " | Interactive forms | browser(click, fill, select_option) | Supports interaction |",
        " | Screenshots | browser(screenshot) | Captures rendered page |",
        " | Multi-page workflows | browser + sequential actions | Maintains session state |",
        " | Infinite scroll / lazy load | browser(scroll) | Loads dynamic content |",
        " | SPA navigation | browser(wait_for_url) | Waits for route change |",
        " | Hover-dependent UI | browser(hover) | Triggers dropdowns/tooltips |",
        " | Cookie management | browser(cookies) | Get/set session cookies |",
        " | Viewport testing | browser(set_viewport) | Responsive testing |",
        " | Raw HTML extraction | browser(extract_html) | DOM structure |",
        " | Link extraction | browser(extract_links) | Structured link list |",
        " | Table extraction | browser(extract_tables) | Structured table data |",
        " | File upload | browser(upload) | Upload to file inputs |",
        "",
        "STATE MANAGEMENT:",
        " - Browser is a global singleton (launched once, reused).",
        ' - Each workflow trace gets its own BrowserContext (isolated cookies).',
        " - State persists within a trace but is isolated between traces.",
        ' - Use action="close" to explicitly clean up.',
        "",
        "SCREENSHOT CLEANUP:",
        " - Screenshots older than 7 days are auto-deleted on startup and every 6 hours.",
        ' - Use action="screenshot" with explicit path= to keep important shots.',
        " - Failure screenshots are saved to workspace/screenshots/error_{trace_id}_{timestamp}.png",
    ],
)
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
    state: str = "visible",
    width: int = 1280,
    height: int = 720,
    cookies_json: str = "",
    action_detail: str = "get",
    retries: int = 0,          # NEW: navigate retry count
) -> dict:
    action = action.strip().lower()

    tracer.step(trace_id, "browser", f"action={action}")

    op_info = DISPATCH.get("browser", {}).get(action)
    if op_info is None:
        valid_actions = " | ".join(sorted(DISPATCH.get("browser", {}).keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
        )

    handler = op_info["func"]

    try:
        result = handler(
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
            state=state,
            width=width,
            height=height,
            cookies_json=cookies_json,
            action_detail=action_detail,
            retries=retries,
        )
    except Exception as e:
        tracer.step(trace_id, "browser", f"action={action}:failed")
        # Skip screenshot-on-failure for screenshot and close actions
        # to avoid cascading failures (e.g., screenshot of a dead page).
        if trace_id and action not in ("screenshot", "close"):
            err_path = _try_failure_screenshot(trace_id)
        else:
            err_path = None
        err_msg = f"Browser action failed: {e}"
        if err_path:
            err_msg += f" (failure screenshot: {err_path})"
        return fail(err_msg, trace_id=trace_id)

    if result.get("status") == "error":
        tracer.step(trace_id, "browser", f"action={action}:failed")
        if trace_id and action not in ("screenshot", "close"):
            err_path = _try_failure_screenshot(trace_id)
            if err_path:
                result["error"] = f"{result['error']} (failure screenshot: {err_path})"
    else:
        tracer.step(trace_id, "browser", f"action={action}:complete")

    return result
