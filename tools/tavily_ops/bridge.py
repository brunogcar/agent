"""tools/tavily_ops/bridge.py — Bridge async Tavily SDK to sync tool interface.

Runs async coroutines in a temporary thread via asyncio.run().
All action handlers call _run_async() (or _run_async_with_resilience)
instead of using asyncio directly.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import time

from core.config import cfg
from core.contracts import fail

# v1.1: Import the circuit breaker from client (same package, avoids circular
# import since client imports bridge at function level inside _close_client).
from tools.tavily_ops.client import _TAVILY_CB


def _run_async(coro):
    """Run an async coroutine in a dedicated thread and return its result.

    v1.1 FIX: Previously used 'with ThreadPoolExecutor() as ex:' which calls
    shutdown(wait=True) on exit. This blocked the caller until the worker
    thread finished — even when future.result(timeout=...) raised TimeoutError.
    The configured timeout provided ZERO actual protection. Now we create the
    executor manually and shut it down with wait=False, letting the caller
    return immediately on timeout while the orphaned thread finishes in the
    background and gets garbage-collected.
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = ex.submit(asyncio.run, coro)
    try:
        return future.result(timeout=cfg.tavily_timeout + 10)
    finally:
        # v1.1: shutdown(wait=False) prevents blocking the caller when the
        # coroutine outlives the timeout. The thread is orphaned and GC'd
        # once it finishes naturally.
        ex.shutdown(wait=False)


# v1.1: Circuit breaker + rate-limit retry wrapper.
# Centralized here so every action gets resilience without per-action edits.
# Actions replace _run_async(_call()) with _run_async_with_resilience(_call()).
def _run_async_with_resilience(coro, trace_id=""):
    """Run a coroutine with circuit breaker and automatic rate-limit backoff.

    - Checks the Tavily circuit breaker before executing.
    - Retries up to 3 times on RateLimitError with exponential backoff (5s, 10s).
    - Records success/failure on the circuit breaker appropriately.
    - Returns the coroutine result, or raises the final exception for the
      action handler's try/except to convert into a fail() dict.
    """
    # Lazy import to avoid hard dependency at module load time.
    try:
        from tavily.errors import RateLimitError
    except ImportError:
        RateLimitError = None

    if not _TAVILY_CB.can_execute():
        # Raise a clear exception that the action handler's except block
        # will catch and convert via _handle_tavily_error.
        raise Exception(
            "Tavily circuit breaker is OPEN. Service temporarily unavailable. "
            "Try again later or use web(search) as fallback."
        )

    last_exception = None
    for attempt in range(3):
        try:
            result = _run_async(coro)
            _TAVILY_CB.record_success()
            return result
        except Exception as e:
            last_exception = e
            # Only retry on RateLimitError; all other exceptions trip the CB.
            if RateLimitError is not None and isinstance(e, RateLimitError):
                if attempt < 2:
                    # Exponential backoff: 5s, 10s
                    backoff = 5 * (2 ** attempt)
                    time.sleep(backoff)
                    continue
            # For timeout, connect, 5xx, or any other failure: trip CB and re-raise.
            _TAVILY_CB.record_failure()
            raise

    # Should never reach here — every path either returns or raises.
    _TAVILY_CB.record_failure()
    raise last_exception
