"""Global state for the browser tool. Thread-safe via _browser_lock."""
from __future__ import annotations

import threading
from typing import Any

# ── Global Browser State ───────────────────────────────────────────────────

_browser = None          # Global Browser instance
_playwright = None       # Global Playwright instance
_contexts: dict[str, tuple[Any, float]] = {}   # trace_id -> (BrowserContext, last_used)
_pages: dict[str, Any] = {}      # trace_id -> Page
_browser_lock = threading.Lock()  # Serializes all browser operations
_reaper_started = False


def reset_state() -> None:
    """Reset all browser state globals. Used by tests."""
    global _browser, _playwright, _reaper_started
    _browser = None
    _playwright = None
    _contexts.clear()
    _pages.clear()
    _reaper_started = False
