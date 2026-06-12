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
import logging
import threading
import time
import uuid
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

# ── Dedicated Browser Event Loop (isolates Playwright from caller loops) ───

_browser_loop: asyncio.AbstractEventLoop | None = None
_browser_thread: threading.Thread | None = None


def _ensure_browser_loop() -> asyncio.AbstractEventLoop:
    """Start a dedicated daemon thread with a permanent event loop for Playwright."""
    global _browser_loop, _browser_thread
    if _browser_loop is not None:
        return _browser_loop
    _browser_loop = asyncio.new_event_loop()
    _browser_thread = threading.Thread(
        target=_browser_loop.run_forever,
        daemon=True,
        name="browser-loop",
    )
    _browser_thread.start()
    _start_reaper()  # Start idle context reaper
    logger.info("[browser] Dedicated event loop thread started")
    return _browser_loop


def _run_browser_async(coro, timeout: float = 60):
    """Run an async coroutine in the dedicated browser loop."""
    loop = _ensure_browser_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ── Global Browser State ───────────────────────────────────────────────────

_browser = None  # Global Browser instance
_playwright = None  # Global Playwright instance
_contexts: dict[str, tuple[Any, float]] = {}  # trace_id -> (BrowserContext, last_used)
_pages: dict[str, Any] = {}  # trace_id -> Page
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
                    _run_browser_async(ctx.close(), timeout=30)
                except Exception:
                    pass
                logger.info("[browser] Reaped idle context for trace %s", tid)

    t = threading.Thread(target=_reap, daemon=True, name="browser-reaper")
    t.start()


def _cleanup_all():
    """Close all browser resources. Called on process exit."""
    global _browser, _playwright, _browser_loop, _browser_thread
    with _browser_lock:
        for tid in list(_pages.keys()):
            _pages.pop(tid, None)
        for tid, (ctx, _) in list(_contexts.items()):
            try:
                _run_browser_async(ctx.close(), timeout=30)
            except Exception:
                pass
            _contexts.pop(tid, None)
        if _browser:
            try:
                _run_browser_async(_browser.close(), timeout=30)
            except Exception:
                pass
            _browser = None
        if _playwright:
            try:
                _run_browser_async(_playwright.stop(), timeout=30)
            except Exception:
                pass
            _playwright = None
    # Stop the dedicated loop so the daemon thread exits cleanly
    if _browser_loop is not None:
        try:
            _browser_loop.call_soon_threadsafe(_browser_loop.stop)
        except Exception:
            pass
        _browser_loop = None


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
    key = trace_id or f"anon_{uuid.uuid4().hex[:8]}"
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
    key = trace_id or f"anon_{uuid.uuid4().hex[:8]}"
    if key in _pages:
        return _pages[key]

    ctx = await _get_or_create_context(trace_id, headless)
    page = await ctx.new_page()

    # Auto-dismiss dialogs to prevent event loop hangs
    page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

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
    """
    action = action.strip().lower()

    # ── navigate ──────────────────────────────────────────────────────────
    if action == "navigate":
        if not url:
            return fail("url is required for navigate action", trace_id=trace_id)
        hostname = urlparse(url).hostname or ""
        if not is_safe_network_address(hostname):
            return fail(f"SSRF blocked: {url}", trace_id=trace_id)

        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                _run_browser_async(
                    page.goto(url, wait_until=wait_until, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
                title = _run_browser_async(page.title(), timeout=10)
            return ok({"url": page.url, "title": title}, trace_id=trace_id)
        except Exception as e:
            return fail(f"Navigation failed: {e}", trace_id=trace_id)

    # ── click ─────────────────────────────────────────────────────────────
    if action == "click":
        if not selector:
            return fail("selector is required for click action", trace_id=trace_id)
        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                _run_browser_async(
                    page.click(selector, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
            return ok({"clicked": True, "selector": selector}, trace_id=trace_id)
        except Exception as e:
            return fail(f"Click failed: {e}", trace_id=trace_id)

    # ── fill ────────────────────────────────────────────────────────────
    if action == "fill":
        if not selector or value is None:
            return fail("selector and value are required for fill action", trace_id=trace_id)
        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                _run_browser_async(
                    page.fill(selector, value, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
            return ok({"filled": True, "selector": selector}, trace_id=trace_id)
        except Exception as e:
            return fail(f"Fill failed: {e}", trace_id=trace_id)

    # ── type ─────────────────────────────────────────────────────────────
    if action == "type":
        if not selector or value is None:
            return fail("selector and value are required for type action", trace_id=trace_id)
        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                _run_browser_async(
                    page.type(selector, value, delay=delay, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
            return ok({"typed": True, "selector": selector}, trace_id=trace_id)
        except Exception as e:
            return fail(f"Type failed: {e}", trace_id=trace_id)

    # ── screenshot ────────────────────────────────────────────────────────
    if action == "screenshot":
        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                screenshot_dir = cfg.workspace_root / "screenshots"
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                if path:
                    save_path = Path(path)
                else:
                    save_path = screenshot_dir / f"{trace_id or 'notrace'}_{int(time.time())}.png"

                if selector:
                    element = _run_browser_async(
                        page.query_selector(selector), timeout=timeout + 5
                    )
                    if not element:
                        return fail(f"Element not found: {selector}", trace_id=trace_id)
                    _run_browser_async(
                        element.screenshot(path=str(save_path)), timeout=timeout + 5
                    )
                else:
                    _run_browser_async(
                        page.screenshot(path=str(save_path), full_page=True),
                        timeout=timeout + 5,
                    )
            return ok({"path": str(save_path)}, trace_id=trace_id)
        except Exception as e:
            return fail(f"Screenshot failed: {e}", trace_id=trace_id)

    # ── text_content ──────────────────────────────────────────────────────
    if action == "text_content":
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

    # ── evaluate ──────────────────────────────────────────────────────────
    if action == "evaluate":
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

    # ── select_option ─────────────────────────────────────────────────────
    if action == "select_option":
        if not selector or value is None:
            return fail("selector and value are required for select_option action", trace_id=trace_id)
        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                _run_browser_async(
                    page.select_option(selector, value, timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
            return ok({"selected": value, "selector": selector}, trace_id=trace_id)
        except Exception as e:
            return fail(f"select_option failed: {e}", trace_id=trace_id)

    # ── keyboard_press ────────────────────────────────────────────────────
    if action == "keyboard_press":
        if not key:
            return fail("key is required for keyboard_press action", trace_id=trace_id)
        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                _run_browser_async(page.keyboard.press(key), timeout=timeout + 5)
            return ok({"pressed": key}, trace_id=trace_id)
        except Exception as e:
            return fail(f"keyboard_press failed: {e}", trace_id=trace_id)

    # ── get_url ─────────────────────────────────────────────────────────
    if action == "get_url":
        try:
            with _browser_lock:
                page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
                current_url = page.url
            return ok({"url": current_url}, trace_id=trace_id)
        except Exception as e:
            return fail(f"get_url failed: {e}", trace_id=trace_id)

    # ── close ─────────────────────────────────────────────────────────────
    if action == "close":
        try:
            with _browser_lock:
                key = trace_id or f"anon_{uuid.uuid4().hex[:8]}"
                if key in _pages:
                    del _pages[key]
                if key in _contexts:
                    ctx, _ = _contexts[key]
                    del _contexts[key]
                    _run_browser_async(ctx.close(), timeout=30)
            return ok({"closed": True}, trace_id=trace_id)
        except Exception as e:
            return fail(f"Close failed: {e}", trace_id=trace_id)

    return fail(
        f"Unknown action '{action}'. Use: navigate | click | fill | type | screenshot | "
        f"text_content | evaluate | select_option | keyboard_press | get_url | close",
        trace_id=trace_id,
    )
