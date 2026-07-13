"""tools/tavily_ops/state.py — Single owner of all Tavily singleton state.

[DESIGN] THIS MODULE IS THE SINGLE OWNER OF ALL TAVILY SINGLETON STATE.

  IMPORT PATTERN — CRITICAL, DO NOT CHANGE:
    client.py MUST import as a module reference:
      from tools.tavily_ops import state
      state._TAVILY_CLIENT = AsyncTavilyClient(...)   # mutates THIS module's attr

    NOT as a name-binding import:
      from tools.tavily_ops.state import _TAVILY_CLIENT  # WRONG

    With from-import, client.py and state.py hold SEPARATE bindings.
    After _get_singleton_client() runs, state._TAVILY_CLIENT stays None.
    reset_state() then resets None->None permanently — a silent no-op.

    This exact bug was confirmed empirically in web_ops v1.0 (two objects, different id()s).
    Fixed in commit b247e7e. tavily_ops was written correctly from day one.
    DO NOT "simplify" back to a from-import.

  HOW TO VERIFY the fix is intact:
    from tools.tavily_ops import client as c, state as s
    _ = c._get_singleton_client()
    assert c.state._TAVILY_CLIENT is s._TAVILY_CLIENT  # must be True
"""
from __future__ import annotations
import threading

# Module-level state for the Tavily client singleton
_TAVILY_CLIENT = None
_TAVILY_CLIENT_KEY = None
_CLIENT_LOCK = threading.Lock()
_KEYLESS_WARNED = False


def reset_state():
    """Reset all module-level state. Used by tests and for cleanup."""
    global _TAVILY_CLIENT, _TAVILY_CLIENT_KEY, _KEYLESS_WARNED
    _TAVILY_CLIENT = None
    _TAVILY_CLIENT_KEY = None
    _KEYLESS_WARNED = False
