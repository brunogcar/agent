"""Global state for the web tool. Thread-safe via _HTTP_CLIENT_LOCK.

Provides reset_state() and reset_loop() for test isolation,
following the browser_ops pattern.


[DESIGN] THIS MODULE IS THE SINGLE OWNER OF ALL WEB SINGLETON STATE.

  IMPORT PATTERN — CRITICAL, DO NOT CHANGE:
    client.py MUST import as a module reference:
      import tools.web_ops.state as state
      state._HTTP_CLIENT = httpx.Client(...)   # mutates THIS module's attr

    NOT as a name-binding import:
      from tools.web_ops.state import _HTTP_CLIENT  # WRONG

    With from-import, after _get_singleton_client() runs, state._HTTP_CLIENT stays None.
    reset_state() resets None->None — permanent no-op. Real client never torn down.

    This bug was confirmed empirically in web_ops v1.0 (two separate Python objects,
    different id()s). Fixed in commit b247e7e. DO NOT revert to from-import.

  HOW TO VERIFY the fix is intact:
    from tools.web_ops import client as c, state as s
    _ = c._get_singleton_client()
    assert c.state._HTTP_CLIENT is s._HTTP_CLIENT  # must be True
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
