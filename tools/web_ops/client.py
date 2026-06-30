"""Singleton httpx.Client management for the web tool.

The singleton client provides connection pooling across all web actions.
httpx.Client is thread-safe; safe to use inside ThreadPoolExecutor.

atexit.register(_close_client) ensures the client is closed on process exit.
"""
from __future__ import annotations

import atexit

import httpx

from tools.web_ops.state import _HTTP_CLIENT, _HTTP_CLIENT_LOCK

_CLIENT_DEFAULTS = {
    "headers": {"User-Agent": "Mozilla/5.0 MCP-Agent/1.0"},
    "timeout": 10.0,
    "follow_redirects": True,
}


def _get_singleton_client() -> httpx.Client:
    """Return the singleton httpx.Client, creating it on first call."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        with _HTTP_CLIENT_LOCK:
            if _HTTP_CLIENT is None:
                _HTTP_CLIENT = httpx.Client(
                    **_CLIENT_DEFAULTS,
                    limits=httpx.Limits(max_connections=20),
                )
    return _HTTP_CLIENT


def _close_client() -> None:
    """Close the singleton client and reset the reference to None."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        try:
            _HTTP_CLIENT.close()
        except Exception:
            pass
        _HTTP_CLIENT = None


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
