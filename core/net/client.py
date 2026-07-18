"""core/net/client.py — Shared HTTP client factory (v1.0).

Standardizes httpx.Client creation across all tools:
  - User-Agent rotation (same pool as web_ops)
  - Timeout defaults
  - Connection limits
  - atexit cleanup

Tools can adopt this incrementally — existing singletons (web_ops/client.py,
github_ops/client.py, vision_ops) still work. New code should use this factory.

Usage:
    from core.net.client import get_shared_client

    client = get_shared_client()
    resp = client.get(url)
    # OR as a context manager (yields the singleton, doesn't close it):
    with shared_client() as client:
        resp = client.get(url)

Design:
  - Singleton per process (thread-safe via double-checked locking)
  - User-Agent selected once at creation (same as web_ops pattern)
  - atexit cleanup registered once
  - Configurable via kwargs on first call (subsequent calls ignore kwargs)
"""
from __future__ import annotations

import atexit
import random
import threading
from typing import Optional

import httpx

# Same UA pool as web_ops/client.py (kept in sync)
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

_CLIENT_DEFAULTS = {
    "timeout": 30.0,
    "follow_redirects": True,
    "limits": httpx.Limits(max_connections=20),
}

_client: Optional[httpx.Client] = None
_lock = threading.Lock()


def get_shared_client(**kwargs) -> httpx.Client:
    """Return the shared httpx.Client singleton.

    On first call, creates the client with the given kwargs (or defaults).
    Subsequent calls ignore kwargs and return the existing singleton.

    Thread-safe via double-checked locking.
    """
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                defaults = {**_CLIENT_DEFAULTS}
                defaults.update(kwargs)
                defaults.setdefault("headers", {})
                if "User-Agent" not in defaults["headers"]:
                    defaults["headers"]["User-Agent"] = random.choice(_USER_AGENTS)
                _client = httpx.Client(**defaults)
    return _client


class _SharedClientContext:
    """Context manager that yields the shared client without closing it."""

    def __enter__(self) -> httpx.Client:
        return get_shared_client()

    def __exit__(self, *args) -> None:
        pass  # Singleton stays alive for connection pooling


def shared_client() -> _SharedClientContext:
    """Return a context manager yielding the shared singleton client."""
    return _SharedClientContext()


def close_shared_client() -> None:
    """Close the shared client and reset the reference to None."""
    global _client
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
            _client = None


atexit.register(close_shared_client)
