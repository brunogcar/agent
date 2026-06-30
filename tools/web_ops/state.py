"""Global state for the web tool. Thread-safe via _HTTP_CLIENT_LOCK.

Provides reset_state() and reset_loop() for test isolation,
following the browser_ops pattern.
"""
from __future__ import annotations

import threading
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

# ── Global Web State ─────────────────────────────────────────────────────

_HTTP_CLIENT: Optional[httpx.Client] = None  # type: ignore
_HTTP_CLIENT_LOCK = threading.Lock()


def reset_state() -> None:
    """Reset all web state globals. Closes the singleton client if open.

    Used by tests to ensure a clean httpx.Client between test cases.
    """
    global _HTTP_CLIENT, _HTTP_CLIENT_LOCK
    if _HTTP_CLIENT is not None:
        try:
            _HTTP_CLIENT.close()
        except Exception:
            pass
        _HTTP_CLIENT = None
    _HTTP_CLIENT_LOCK = threading.Lock()


def reset_loop() -> None:
    """No-op for web tool compatibility with test fixtures.

    The web tool has no async event loop (unlike browser).
    This function exists so conftest.py can call it uniformly.
    """
    pass
