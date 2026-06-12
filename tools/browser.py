"""
tools/browser.py — Playwright-based browser automation.
Global singleton browser with trace-scoped contexts for isolation.

Actions:
  navigate, click, fill, type, screenshot, text_content, evaluate,
  select_option, keyboard_press, get_url, close

NOT_PARALLEL_SAFE: Browser is stateful and heavy. All calls are serialized
via a module-level threading.Lock().

Future DeepResearch workflow will use browser as a fallback for JS-heavy
sites and for interactive tasks (forms, pagination, auth).
See docs/BROWSER.md for full documentation.
"""
from __future__ import annotations

import asyncio
import atexit
import base64
import concurrent.futures
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from registry import tool
from core.config import cfg
from core.contracts import ok, fail
from core.security import is_safe_network_address

logger = logging.getLogger(__name__)

# Module-level flags
PARALLEL_SAFE = False

# ── Async-to-Sync Bridge ───────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine from a sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(asyncio.run, coro)
        return future.result(timeout=60)


# ── Global Browser State ───────────────────────────────────────────────────

_browser = None          # Global Browser instance
_playwright = None       # Global Playwright instance
_contexts: dict[str, tuple[Any, float]] = {}   # trace_id -> (BrowserContext, last_used)
_pages: dict[str, Any] = {}      # trace_id -> Page
_browser_lock = threading.Lock()  # Serializes all browser operations
_reaper_started = False

# ── Lifecycle Management ───────────────────────────────────────────────────

def _start_reaper():
    """Start background daemon thread to close idle contexts."""
    global _reaper_started
    if _reaper_started:
        return
    _reaper_started = True

    def _reap():
        while True:
            time.sleep(60)
            now = time.time()
            to_close = []
            with _browser_lock:
                for tid, (ctx, last_used) in list(_contexts.items()):
                    if now - last_used > 600:  # 10 minutes idle
                        to_close.append((tid, ctx))
                for tid, _ in to_close:
                    if tid in _pages:
                        del _pages[tid]
                    del _contexts[tid]
            for tid, ctx in to_close:
                try:
                    _run_async(ctx.close())
                except Exception:
                    pass
                logger.info("[browser] Reaped idle context for trace %s", tid)

    t = threading.Thread(target=_reap, daemon=True, name="browser-reaper")
    t.start()


def _cleanup_all():
    """Close all browser resources. Called on process exit."""
    global _browser, _playwright
    with _browser_lock:
        for tid in list(_pages.keys()):
            _pages.pop(tid, None)
        for tid, (ctx, _) in list(_contexts.items()):
            try:
                _run_async(ctx.close())
            except Exception:
                pass
            _contexts.pop(tid, None)
        if _browser:
            try:
                _run_async(_browser.close())
            except Exception:
                pass
            _browser = None
        if _playwright:
            try:
                _run_async(_playwright.stop())
            except Exception:
                pass
            _playwright = None


atexit.register(_cleanup_all)

# ── Browser Initialization ─────────────────────────────────────────────────

async def _launch_browser(headless: bool = True):
    """Launch Playwright browser if not already running."""
    global _browser, _playwright
    if _browser is None:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().__aenter__()
        _browser = await _playwright.chromium.launch(headless=headless)
    return _browser


async def _get_or_create_context(trace_id: str, headless: bool = True):
    """Get existing context for trace or create a new one."""
    key = trace_id or "__default__"
    if key in _contexts:
        ctx, _ = _contexts[key]
        _contexts[key] = (ctx, time.time())
        return ctx

    browser = await _launch_browser(headless)
    ctx = await browser.new_context(
        downloads_path=str(cfg.workspace_root / "browser_downloads" / key)
    )
    _contexts[key] = (ctx, time.time())
    return ctx


async def _get_page(trace_id: str, headless: bool = True):
    """Get or create a page for the given trace."""
    key = trace_id or "__default__"
    if key in _pages:
        return _pages[key]

    ctx = await _get_or_create_context(trace_id, headless)
    page = await ctx.new_page()

    # Auto-dismiss dialogs to prevent event loop hangs
    page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

    _pages[key] = page
    return page


# ── Tool Facade ─────────────────────────────────────────────────────────────

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
      path (optional): Save path (default: workspace/screenshots/{trace_id}.png)
      return_base64 (default: False): Return base64-encoded image (max 100KB)

    text_content: Extract text from element
      selector (required): CSS selector (default: "body")

    evaluate: Run JavaScript
      expression (required): JS code to execute (e.g., "document.title")

    select_option: Select dropdown option
      selector (required): CSS selector for <select>
      value (required): Option value or label

    keyboard_press: Press a key
      key (required): Key to press (e.g., "Enter", "Tab")

    get_url: Get current URL
    close: Close browser context for this trace

    IMPORTANT:
    - Browser is NOT parallel-safe. Concurrent calls are serialized.
    - Screenshots are saved to disk by default. Use return_base64 only for small images.
    - Always call action="close" at the end of your workflow to free resources.
    """
    _start_reaper()

    action = action.strip().lower()

    if action == "close":
        with _browser_lock:
            key = trace_id or "__default__"
            if key in _pages:
                del _pages[key]
            if key in _contexts:
                ctx, _ = _contexts.pop(key)
                try:
                    _run_async(ctx.close())
                except Exception:
                    pass
        return ok({"closed": True}, trace_id=trace_id)

    with _browser_lock:
        try:
            page = _run_async(_get_page(trace_id, headless))

            if action == "navigate":
                if not url:
                    return fail("url is required for navigate action", trace_id=trace_id)
                if not is_safe_network_address(urlparse(url).hostname or ""):
                    return fail(f"SSRF blocked: {url}", trace_id=trace_id)

                _run_async(
                    page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                )
                return ok(
                    {
                        "url": page.url,
                        "title": _run_async(page.title()),
                    },
                    trace_id=trace_id,
                )

            if action == "click":
                if not selector:
                    return fail(
                        "selector is required for click action", trace_id=trace_id
                    )
                _run_async(page.click(selector, timeout=timeout * 1000))
                return ok(
                    {"selector": selector, "clicked": True}, trace_id=trace_id
                )

            if action == "fill":
                if not selector or value is None:
                    return fail(
                        "selector and value are required for fill action",
                        trace_id=trace_id,
                    )
                _run_async(page.fill(selector, value, timeout=timeout * 1000))
                return ok(
                    {"selector": selector, "filled": True}, trace_id=trace_id
                )

            if action == "type":
                if not selector or value is None:
                    return fail(
                        "selector and value are required for type action",
                        trace_id=trace_id,
                    )
                _run_async(page.type(selector, value, delay=delay))
                return ok(
                    {"selector": selector, "typed": True}, trace_id=trace_id
                )

            if action == "screenshot":
                screenshot_dir = cfg.workspace_root / "screenshots"
                screenshot_dir.mkdir(parents=True, exist_ok=True)

                if not path:
                    path = str(
                        screenshot_dir
                        / f"{trace_id or 'default'}_{int(time.time())}.png"
                    )

                if selector:
                    element = _run_async(page.query_selector(selector))
                    if not element:
                        return fail(
                            f"Selector '{selector}' not found", trace_id=trace_id
                        )
                    _run_async(element.screenshot(path=path))
                else:
                    _run_async(page.screenshot(path=path, full_page=True))

                result = {"path": path}

                if return_base64:
                    try:
                        with open(path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        if len(b64) <= 100_000:  # 100KB cap
                            result["base64"] = b64
                        else:
                            result["base64"] = (
                                b64[:100_000]
                                + "... [truncated: full image at path]"
                            )
                    except Exception:
                        pass  # Non-fatal: path is still valid

                return ok(result, trace_id=trace_id)

            if action == "text_content":
                sel = selector or "body"
                text = _run_async(
                    page.text_content(sel, timeout=timeout * 1000)
                )
                return ok({"selector": sel, "text": text or ""}, trace_id=trace_id)

            if action == "evaluate":
                if not expression:
                    return fail(
                        "expression is required for evaluate action",
                        trace_id=trace_id,
                    )
                result = _run_async(page.evaluate(expression))
                return ok(
                    {"expression": expression, "result": result},
                    trace_id=trace_id,
                )

            if action == "select_option":
                if not selector or value is None:
                    return fail(
                        "selector and value are required for select_option action",
                        trace_id=trace_id,
                    )
                _run_async(
                    page.select_option(selector, value, timeout=timeout * 1000)
                )
                return ok(
                    {"selector": selector, "selected": value},
                    trace_id=trace_id,
                )

            if action == "keyboard_press":
                if not key:
                    return fail(
                        "key is required for keyboard_press action",
                        trace_id=trace_id,
                    )
                _run_async(page.keyboard.press(key))
                return ok({"key": key, "pressed": True}, trace_id=trace_id)

            if action == "get_url":
                return ok({"url": page.url}, trace_id=trace_id)

            return fail(
                f"Unknown action '{action}'. Use: navigate | click | fill | type | screenshot | "
                "text_content | evaluate | select_option | keyboard_press | get_url | close",
                trace_id=trace_id,
            )

        except Exception as e:
            # Cleanup on error to prevent zombie state
            key = trace_id or "__default__"
            if key in _pages:
                del _pages[key]
            if key in _contexts:
                ctx, _ = _contexts.pop(key)
                try:
                    _run_async(ctx.close())
                except Exception:
                    pass
            return fail(f"Browser error: {type(e).__name__}: {e}", trace_id=trace_id)
