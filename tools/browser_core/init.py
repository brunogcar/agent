"""Browser and Playwright initialization."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from core.config import cfg
from tools.browser_core.state import _browser, _playwright, _contexts, _pages
from tools.browser_core.loop import _ensure_browser_loop, _run_browser_async
from tools.browser_core.lifecycle import _start_reaper


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
