"""browser_core/actions.py — Browser action handlers.

Each action is a standalone sync function that calls Playwright via the
_run_browser_async bridge.  The DISPATCH dict maps action names to handlers
for the thin facade in tools/browser.py.

Phase 3 additions:
  • scroll          — scroll page or element
  • wait_for_url    — wait for navigation to a specific URL

Phase 6 additions:
  • DISPATCH_METADATA — action metadata for error messages and future docs
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
import uuid
from typing import Any
from urllib.parse import urlparse

from core.contracts import fail, ok
from core.security import is_safe_network_address
from core.tracer import tracer
from core.config import cfg

from tools.browser_core.init import _get_page
from tools.browser_core.loop import _run_browser_async
from tools.browser_core.state import _browser_lock, _contexts, _pages

logger = logging.getLogger(__name__)

# ── Action Handlers ────────────────────────────────────────────────────────


def _action_navigate(
    url: str,
    wait_until: str = "domcontentloaded",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Navigate to a URL and wait for the page to load."""
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


def _action_click(
    selector: str,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Click an element by CSS selector."""
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


def _action_fill(
    selector: str,
    value: str,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Clear and type into an input field."""
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


def _action_type(
    selector: str,
    value: str,
    delay: int = 50,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Type with human-like delay between keystrokes."""
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


def _action_screenshot(
    selector: str = "",
    path: str = "",
    timeout: int = 30,
    headless: bool = True,
    return_base64: bool = False,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Capture a screenshot of the page or a specific element."""
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

            result = {"path": str(save_path)}
            # TODO: Phase 5 — implement return_base64 encoding
            # if return_base64:
            #     try:
            #         with open(save_path, "rb") as f:
            #             b64 = base64.b64encode(f.read()).decode()
            #         result["base64"] = b64
            #     except Exception:
            #         pass
            return ok(result, trace_id=trace_id)
    except Exception as e:
        return fail(f"Screenshot failed: {e}", trace_id=trace_id)


def _action_text_content(
    selector: str = "",
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
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


def _action_evaluate(
    expression: str,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Run JavaScript on the page and return the result."""
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


def _action_select_option(
    selector: str,
    value: str,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Select an option from a <select> dropdown."""
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


def _action_keyboard_press(
    key: str,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Press a keyboard key (Enter, Tab, Escape, etc.)."""
    if not key:
        return fail("key is required for keyboard_press action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(page.keyboard.press(key), timeout=timeout + 5)
        return ok({"pressed": key}, trace_id=trace_id)
    except Exception as e:
        return fail(f"keyboard_press failed: {e}", trace_id=trace_id)


def _action_get_url(
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Return the current page URL."""
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            current_url = page.url
        return ok({"url": current_url}, trace_id=trace_id)
    except Exception as e:
        return fail(f"get_url failed: {e}", trace_id=trace_id)


def _action_close(
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Close the browser context for this trace."""
    try:
        with _browser_lock:
            ctx_key = trace_id or f"anon_{uuid.uuid4().hex[:8]}"
            if ctx_key in _pages:
                del _pages[ctx_key]
            if ctx_key in _contexts:
                ctx, _ = _contexts[ctx_key]
                del _contexts[ctx_key]
                _run_browser_async(ctx.close(), timeout=30)
        return ok({"closed": True}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Close failed: {e}", trace_id=trace_id)


# ── Phase 3: New Actions ───────────────────────────────────────────────────


def _action_wait_for_selector(
    selector: str,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Wait for an element to appear in the DOM.

    Useful after clicks that trigger dynamic content, or before interacting
    with elements that load lazily.  Required by scroll and upload actions.
    """
    if not selector:
        return fail("selector is required for wait_for_selector action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.wait_for_selector(selector, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"waited": True, "selector": selector}, trace_id=trace_id)
    except Exception as e:
        return fail(f"wait_for_selector failed: {e}", trace_id=trace_id)


def _action_scroll(
    selector: str = "",
    direction: str = "bottom",
    amount: int = 0,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Scroll the page or a specific element.

    Parameters
    ----------
    selector : str
        CSS selector of the element to scroll (default: page body).
    direction : str
        "top" | "bottom" | "up" | "down" — preset scroll directions.
    amount : int
        Pixels to scroll (default: 0 = full height for top/bottom).
    """
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)

            if selector:
                # Scroll element into view
                element = _run_browser_async(
                    page.query_selector(selector), timeout=timeout + 5
                )
                if not element:
                    return fail(f"Element not found: {selector}", trace_id=trace_id)
                _run_browser_async(
                    element.scroll_into_view_if_needed(), timeout=timeout + 5
                )
                return ok({"scrolled": True, "selector": selector}, trace_id=trace_id)

            # Page-level scroll via JS
            js_map = {
                "top": "window.scrollTo(0, 0)",
                "bottom": "window.scrollTo(0, document.body.scrollHeight)",
                "up": f"window.scrollBy(0, -{amount or 1000})",
                "down": f"window.scrollBy(0, {amount or 1000})",
            }
            js = js_map.get(direction, js_map["bottom"])
            _run_browser_async(page.evaluate(js), timeout=timeout + 5)

        return ok({"scrolled": True, "direction": direction, "amount": amount}, trace_id=trace_id)
    except Exception as e:
        return fail(f"Scroll failed: {e}", trace_id=trace_id)


def _action_wait_for_url(
    url: str,
    timeout: int = 30,
    headless: bool = True,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Wait for the current page URL to match a pattern.

    Useful after clicks that trigger navigation (form submits, SPA route
    changes) where the next action must run on the new page.
    """
    if not url:
        return fail("url is required for wait_for_url action", trace_id=trace_id)
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            _run_browser_async(
                page.wait_for_url(url, timeout=timeout * 1000),
                timeout=timeout + 5,
            )
        return ok({"waited": True, "url": page.url}, trace_id=trace_id)
    except Exception as e:
        return fail(f"wait_for_url failed: {e}", trace_id=trace_id)


# ── Dispatch ────────────────────────────────────────────────────────────────

DISPATCH = {
    "navigate": _action_navigate,
    "click": _action_click,
    "fill": _action_fill,
    "type": _action_type,
    "screenshot": _action_screenshot,
    "text_content": _action_text_content,
    "evaluate": _action_evaluate,
    "select_option": _action_select_option,
    "keyboard_press": _action_keyboard_press,
    "get_url": _action_get_url,
    "close": _action_close,
    # Phase 3
    "wait_for_selector": _action_wait_for_selector,
    "scroll": _action_scroll,
    "wait_for_url": _action_wait_for_url,
}

# Phase 6: DISPATCH_METADATA — action metadata for error messages and docs.
# Keys match DISPATCH.  Each entry lists required params and optional params.
DISPATCH_METADATA = {
    "navigate": {
        "required": ["url"],
        "optional": ["wait_until", "timeout", "headless"],
        "description": "Go to URL and wait for load",
    },
    "click": {
        "required": ["selector"],
        "optional": ["timeout", "headless"],
        "description": "Click an element",
    },
    "fill": {
        "required": ["selector", "value"],
        "optional": ["timeout", "headless"],
        "description": "Clear and type into an input",
    },
    "type": {
        "required": ["selector", "value"],
        "optional": ["delay", "timeout", "headless"],
        "description": "Type with human-like delay",
    },
    "screenshot": {
        "required": [],
        "optional": ["selector", "path", "timeout", "headless", "return_base64"],
        "description": "Capture page or element screenshot",
    },
    "text_content": {
        "required": [],
        "optional": ["selector", "timeout", "headless"],
        "description": "Extract text from element",
    },
    "evaluate": {
        "required": ["expression"],
        "optional": ["timeout", "headless"],
        "description": "Run JavaScript",
    },
    "select_option": {
        "required": ["selector", "value"],
        "optional": ["timeout", "headless"],
        "description": "Select dropdown option",
    },
    "keyboard_press": {
        "required": ["key"],
        "optional": ["timeout", "headless"],
        "description": "Press a key",
    },
    "get_url": {
        "required": [],
        "optional": ["timeout", "headless"],
        "description": "Return current page URL",
    },
    "close": {
        "required": [],
        "optional": ["trace_id"],
        "description": "Close browser context for this trace",
    },
    "wait_for_selector": {
        "required": ["selector"],
        "optional": ["timeout", "headless"],
        "description": "Wait for element to appear in DOM",
    },
    "scroll": {
        "required": [],
        "optional": ["selector", "direction", "amount", "timeout", "headless"],
        "description": "Scroll page or element",
    },
    "wait_for_url": {
        "required": ["url"],
        "optional": ["timeout", "headless"],
        "description": "Wait for URL to match pattern",
    },
}
