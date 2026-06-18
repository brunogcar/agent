"""Action handlers for the browser tool."""
from __future__ import annotations

import base64
import threading
import uuid
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.contracts import ok, fail
from core.security import is_safe_network_address
from core.config import cfg
from tools.browser_core.state import _browser_lock
from tools.browser_core.init import _get_page
from tools.browser_core.loop import _run_browser_async


# ── Action Handlers ────────────────────────────────────────────────────────

def _action_navigate(
    *,
    url: str,
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
    *,
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
    *,
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
    *,
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
    *,
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
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            screenshot_dir = cfg.agent_root / "tmp" / "screenshots"
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


def _action_text_content(
    *,
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
    *,
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
    *,
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
    *,
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
    *,
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
    try:
        with _browser_lock:
            page = _run_browser_async(_get_page(trace_id, headless), timeout=timeout + 5)
            current_url = page.url
        return ok({"url": current_url}, trace_id=trace_id)
    except Exception as e:
        return fail(f"get_url failed: {e}", trace_id=trace_id)


def _action_close(
    *,
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
    try:
        with _browser_lock:
            from tools.browser_core.state import _contexts, _pages
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


def _action_wait_for_selector(
    *,
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


# ── Dispatch ───────────────────────────────────────────────────────────────

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
    "wait_for_selector": _action_wait_for_selector,
}

DISPATCH_METADATA = {
    "navigate": {"required": ["url"], "optional": ["wait_until", "timeout", "headless"]},
    "click": {"required": ["selector"], "optional": ["timeout", "headless"]},
    "fill": {"required": ["selector", "value"], "optional": ["timeout", "headless"]},
    "type": {"required": ["selector", "value"], "optional": ["delay", "timeout", "headless"]},
    "screenshot": {"required": [], "optional": ["selector", "path", "timeout", "headless"]},
    "text_content": {"required": [], "optional": ["selector", "timeout", "headless"]},
    "evaluate": {"required": ["expression"], "optional": ["timeout", "headless"]},
    "select_option": {"required": ["selector", "value"], "optional": ["timeout", "headless"]},
    "keyboard_press": {"required": ["key"], "optional": ["timeout", "headless"]},
    "get_url": {"required": [], "optional": ["timeout", "headless"]},
    "close": {"required": [], "optional": []},
    "wait_for_selector": {"required": ["selector"], "optional": ["timeout", "headless"]},
}
