"""tools/tavily_ops/client.py — AsyncTavilyClient singleton + lifecycle.

v1.2 FIXES:
- _close_client acquires _CLIENT_LOCK to prevent race.
- _get_singleton_client closes old client on key change (prevents leak).
- Restore api_key or None for keyless mode safety.
- Log exceptions in _close_client instead of swallowing.
v1.3 FIXES:
- Use _run_async for client.close() instead of fresh ThreadPoolExecutor.
- Register Tavily SDK RateLimitError as retryable.
- FIXED: _warn_keyless_once() now uses state._KEYLESS_WARNED for proper reset_state() support.


[DESIGN] KEY DECISIONS — read before modifying:

  1. ALL state mutations go through 'from tools.tavily_ops import state'.
     See state.py for the full module-ref vs from-import explanation.

  2. AsyncTavilyClient.close() is a COROUTINE — must be awaited.
     Nulling state._TAVILY_CLIENT without awaiting close() leaks the underlying
     httpx connection pool. Use bridge._run_async(state._TAVILY_CLIENT.close()).

  3. atexit path goes through _close_client() -> _close_client_locked() ->
     _run_async() -> bridge.py which uses shutdown(wait=False).
     This is the same non-blocking shutdown as all other paths. The ~10s timeout
     in _run_async (cfg.tavily_timeout + 10) bounds the close attempt.
     DO NOT change atexit to use shutdown(wait=True) — it would block process
     exit on a hung async close.

  4. Keyless mode: always pass api_key=None, NOT api_key="".
     The SDK treats "" differently from None in some versions.
"""
from __future__ import annotations

import atexit
import logging

from core.config import cfg
from core.llm_backend.circuit_breaker import CircuitBreaker
from core.net.errors import register_retryable_exception
from tools.tavily_ops import state

logger = logging.getLogger(__name__)


def _is_keyless_mode():
    """Return True if Tavily API key is not configured."""
    return not getattr(cfg, "tavily_api_key", None)


# v1.1: Backward-compatible alias
_is_keyless = _is_keyless_mode


def _get_singleton_client():
    """Return the singleton AsyncTavilyClient, creating it if needed.

    Thread-safe via _CLIENT_LOCK.
    v1.2 FIX: Closes old client when API key changes to prevent pool leak.
    """
    from tavily import AsyncTavilyClient

    # v1.2 FIX: Restore `or None` to ensure SDK gets None for keyless mode
    current_key = cfg.tavily_api_key or None

    with state._CLIENT_LOCK:
        if state._TAVILY_CLIENT is not None and state._TAVILY_CLIENT_KEY == current_key:
            return state._TAVILY_CLIENT

        # v1.2 FIX: Close old client before creating new one
        if state._TAVILY_CLIENT is not None:
            _close_client_locked()

        state._TAVILY_CLIENT = AsyncTavilyClient(api_key=current_key)
        state._TAVILY_CLIENT_KEY = current_key
        return state._TAVILY_CLIENT


def _close_client():
    """Close the Tavily client and clear singleton state.

    v1.2 FIX: Acquires _CLIENT_LOCK to prevent race with _get_singleton_client.
    Logs exceptions instead of silently swallowing.
    """
    with state._CLIENT_LOCK:
        _close_client_locked()


def _close_client_locked():
    """Internal: close client while holding _CLIENT_LOCK.

    v1.3 FIX: Use _run_async() instead of creating a fresh ThreadPoolExecutor.
    """
    if state._TAVILY_CLIENT is not None:
        try:
            if hasattr(state._TAVILY_CLIENT, "close"):
                from tools.tavily_ops.bridge import _run_async
                _run_async(state._TAVILY_CLIENT.close())
        except Exception as e:
            # v1.2 FIX: Log instead of silently swallowing
            logger.warning("Failed to close Tavily client: %s", e)
        finally:
            state._TAVILY_CLIENT = None
            state._TAVILY_CLIENT_KEY = None


# v1.1: Register atexit handler for clean shutdown
atexit.register(_close_client)

# ── Circuit Breaker ──────────────────────────────────────────────────────────
_TAVILY_CB = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    half_open_max_calls=1,
)

# v1.3: Register Tavily SDK exceptions as retryable
try:
    from tavily.errors import RateLimitError
    register_retryable_exception(RateLimitError)
except ImportError:
    pass  # tavily-python not installed


def _warn_keyless_once():
    """Log a one-time warning when running in keyless mode.

    v1.3 FIX: Uses state._KEYLESS_WARNED so reset_state() properly clears it.
    """
    if not state._KEYLESS_WARNED:
        logger.warning(
            "Tavily running in keyless mode. "
            "Set TAVILY_API_KEY in .env for full access."
        )
        state._KEYLESS_WARNED = True
