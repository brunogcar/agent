"""tools/tavily_ops/client.py — Singleton AsyncTavilyClient with lazy init.

Handles API key resolution, keyless mode detection, and double-checked locking
for thread-safe singleton creation. The import pattern (import module, mutate
module attribute) is deliberately chosen to prevent the name-binding divergence
bug that affected the web_ops refactor.
"""
from __future__ import annotations

import atexit
import logging
import threading

from core.config import cfg
from core.llm_backend.circuit_breaker import CircuitBreaker

# v1.1: Circuit breaker for Tavily API resilience.
# Trips after 3 consecutive failures, recovers after 60s.
# Imported by bridge.py for the _run_async_with_resilience wrapper.
_TAVILY_CB = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

# Import state module by reference (not from-statement) to avoid the
# name-binding divergence bug that broke the web_ops refactor.
import tools.tavily_ops.state as state

logger = logging.getLogger(__name__)


def _is_keyless_mode():
    """Return True if no Tavily API key is configured (free tier)."""
    return not cfg.tavily_api_key


# v1.1: Backward-compatible alias used by extract.py and research.py.
def _is_keyless():
    """Alias for _is_keyless_mode(). Kept for backward compatibility."""
    return _is_keyless_mode()


# v1.1: Added for keyless warning test compatibility.
def _warn_keyless_once():
    """Log a one-time warning about keyless mode limitations.

    Uses state._KEYLESS_WARNED to ensure the warning is only emitted once
    per process lifetime (or until reset_state() is called).
    """
    if not state._KEYLESS_WARNED:
        logger.warning(
            "Tavily running in keyless mode. "
            "Rate limits and features are reduced. "
            "Set TAVILY_API_KEY in .env for full access."
        )
        state._KEYLESS_WARNED = True


def _get_singleton_client():
    """Lazy-create the AsyncTavilyClient singleton with double-checked locking.

    The outer check avoids locking on every call; the inner check prevents
    race conditions when multiple threads try to create the client simultaneously.
    If the API key changes, the old client is discarded and a new one created.
    """
    current_key = cfg.tavily_api_key
    if state._TAVILY_CLIENT is not None and state._TAVILY_CLIENT_KEY == current_key:
        return state._TAVILY_CLIENT

    with state._CLIENT_LOCK:
        if state._TAVILY_CLIENT is not None and state._TAVILY_CLIENT_KEY == current_key:
            return state._TAVILY_CLIENT

        try:
            from tavily import AsyncTavilyClient
        except ImportError:
            raise ImportError(
                "tavily-python is not installed. "
                "Install it with: pip install tavily-python"
            )

        state._TAVILY_CLIENT = AsyncTavilyClient(api_key=current_key)
        state._TAVILY_CLIENT_KEY = current_key
        return state._TAVILY_CLIENT


def _close_client():
    """Close the Tavily client and clear singleton state.

    v1.1 FIX: Previously this function checked for a running loop via
    asyncio.get_running_loop() but never actually called client.close(),
    leaving the underlying httpx connection pool unreleased. Now it reuses
    bridge._run_async (which already solves "run coroutine from sync context")
    to properly await the async close() coroutine.
    """
    if state._TAVILY_CLIENT is not None:
        try:
            if hasattr(state._TAVILY_CLIENT, "close"):
                # v1.1: Actually close the client. AsyncTavilyClient.close()
                # is a coroutine that must be awaited. We reuse bridge._run_async
                # which already handles "run coroutine from sync context".
                # Import here to avoid circular dependency at module load.
                from tools.tavily_ops import bridge
                bridge._run_async(state._TAVILY_CLIENT.close())
        except Exception:
            pass
        finally:
            state._TAVILY_CLIENT = None
            state._TAVILY_CLIENT_KEY = None


atexit.register(_close_client)
