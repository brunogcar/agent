"""Dedicated event loop for Playwright to avoid blocking the main thread."""
from __future__ import annotations

import asyncio
import threading
from typing import Any

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
    # Start idle context reaper
    from tools.browser_core.lifecycle import _start_reaper
    _start_reaper()
    return _browser_loop


def _run_browser_async(coro, timeout: float):
    """Run an async coroutine in the dedicated browser loop.

    NOTE: timeout is REQUIRED (no default) to prevent silent override of
    per-action user timeouts. Callers must always pass an explicit timeout.
    """
    loop = _ensure_browser_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def reset_loop() -> None:
    """Reset loop globals. Used by tests."""
    global _browser_loop, _browser_thread
    _browser_loop = None
    _browser_thread = None
