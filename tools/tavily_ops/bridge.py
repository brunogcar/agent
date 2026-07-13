"""tools/tavily_ops/bridge.py — Async bridge + circuit breaker + retry.

v1.2 FIXES:
- Accept coroutine factory (callable) instead of coroutine object for retry.
- Use core/net/errors.py for unified retry classification.
- Always use ThreadPoolExecutor (removes fast path that breaks in pytest/event loops).
- Shorter default backoff to prevent worker pool exhaustion.
v1.3 FIXES:
- Use retry_async_factory from core.net.retry for unified retry logic.
- Added CircuitBreakerOpen exception for proper error_code propagation.
- Removed dead code after retry loop.


[DESIGN] KEY DECISIONS — read before modifying:

  1. ALWAYS USE ThreadPoolExecutor — NEVER call asyncio.run() directly.
     asyncio.run() raises RuntimeError inside an already-running event loop (pytest,
     Jupyter, nested async contexts). ThreadPoolExecutor runs asyncio in a new thread.
     DO NOT add a "fast path" that calls asyncio.run() — it WILL break in tests.

  2. Use shutdown(wait=False), NOT 'with ThreadPoolExecutor() as ex:'.
     'with' calls shutdown(wait=True) on exit, blocking until the thread finishes.
     This NEGATES the timeout. Tested empirically: 1s timeout with 'with' blocks
     for the full 3s coroutine duration before TimeoutError fires.

  3. Pass the FACTORY (callable) to retry_async_factory, NOT the coroutine result.
     CORRECT: _run_async_with_resilience(_call, trace_id=...)
     WRONG:   _run_async_with_resilience(_call(), trace_id=...)
     A Python coroutine is one-shot. Re-awaiting after a raise gives:
       RuntimeError: cannot reuse already awaited coroutine
     This bug shipped in tavily v1.0/v1.1. Fixed in v1.2.

  4. DELIBERATE CHOICE: per-call executor, not a persistent background loop.
     browser_ops uses a persistent loop for Playwright (needs session continuity).
     Tavily has NO inter-call state. DO NOT unify with browser_ops' approach.

  5. on_failure fires ONLY on final raise (retry exhaustion), NOT per retry attempt.
     This was fixed in core/net/retry.py v1.5 — on_failure is called only after all
     retries are exhausted, not after each individual failure. This prevents transient
     retries from accumulating CB failure_count on overall-successful calls.
     DO NOT revert retry.py to per-attempt on_failure firing.
"""
from __future__ import annotations

import concurrent.futures
import time
import asyncio

from core.config import cfg
from core.net.errors import is_retryable_error, get_retry_delay
from core.net.retry import retry_async_factory
from tools.tavily_ops.client import _TAVILY_CB

class CircuitBreakerOpen(Exception):
    """Raised when the Tavily circuit breaker is OPEN.

    v1.3: Dedicated exception so _handle_tavily_error can return error_code=CB_OPEN.
    """
    pass


def _run_async(coro):
    """Run an async coroutine from synchronous code using ThreadPoolExecutor.

    Always uses ThreadPoolExecutor for consistency across environments
    (pytest, production, event loops).
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = ex.submit(asyncio.run, coro)
    try:
        return future.result(timeout=cfg.tavily_timeout + 10)
    finally:
        ex.shutdown(wait=False)


def _run_async_with_resilience(coro_factory, trace_id=""):
    """Run a coroutine factory with circuit breaker and retry.

    Args:
        coro_factory: A callable that returns a fresh coroutine each time.
            Pass the function itself, NOT the result of calling it:
            CORRECT: _run_async_with_resilience(_call, trace_id=...)
            WRONG: _run_async_with_resilience(_call(), trace_id=...)
        trace_id: Optional trace ID for observability.

    Returns:
        The coroutine's return value.

    Raises:
        CircuitBreakerOpen: If circuit breaker is OPEN.
        Exception: If all retries are exhausted.
    """
    if not _TAVILY_CB.can_execute():
        raise CircuitBreakerOpen(
            "Tavily circuit breaker is OPEN — too many consecutive failures. "
            "Try again later or use web(search) as fallback."
        )

    # v1.3: Use unified retry_async_factory from core.net.retry
    return retry_async_factory(
        coro_factory,
        run_async=_run_async,
        max_retries=3,
        base_delay=2.0,
        max_delay=10.0,
        jitter=True,
        is_retryable=is_retryable_error,
        on_success=_TAVILY_CB.record_success,
        on_failure=_TAVILY_CB.record_failure,
    )
