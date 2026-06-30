"""Singleton httpx.Client management for the web tool.

The singleton client provides connection pooling across all web actions.
httpx.Client is thread-safe; safe to use inside ThreadPoolExecutor.

atexit.register(_close_client) ensures the client is closed on process exit.
"""
from __future__ import annotations

import atexit
import random

import httpx

import tools.web_ops.state as state

# Rotating user-agent pool to reduce 403 blocks from sites that filter
# on the default UA string.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

_CLIENT_DEFAULTS = {
    "timeout": 10.0,
    "follow_redirects": True,
}


def _pick_user_agent() -> str:
    """Return a random user agent from the rotation pool."""
    return random.choice(_USER_AGENTS)


def _get_singleton_client() -> httpx.Client:
    """Return the singleton httpx.Client, creating it on first call."""
    if state._HTTP_CLIENT is None:
        with state._HTTP_CLIENT_LOCK:
            if state._HTTP_CLIENT is None:
                state._HTTP_CLIENT = httpx.Client(
                    headers={"User-Agent": _pick_user_agent()},
                    **_CLIENT_DEFAULTS,
                    limits=httpx.Limits(max_connections=20),
                )
    return state._HTTP_CLIENT


def _close_client() -> None:
    """Close the singleton client and reset the reference to None."""
    if state._HTTP_CLIENT is not None:
        try:
            state._HTTP_CLIENT.close()
        except Exception:
            pass
        state._HTTP_CLIENT = None


# Register cleanup exactly once, here in client.py.
atexit.register(_close_client)


class _SingletonClientContext:
    """Context manager that yields the singleton client without closing it.

    This exists so action code can use `with _make_client() as client:`
    for consistency, even though the singleton is never closed on exit.
    """
    def __enter__(self) -> httpx.Client:
        return _get_singleton_client()

    def __exit__(self, *args) -> None:
        pass  # Singleton stays alive for connection pooling


def _make_client() -> _SingletonClientContext:
    """Return a context manager yielding the pooled singleton client."""
    return _SingletonClientContext()


def _get_client() -> httpx.Client:
    """Legacy compatibility wrapper — returns the singleton client.

    Deprecated: use _get_singleton_client() or _make_client() directly.
    """
    return _get_singleton_client()
