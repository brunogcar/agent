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
