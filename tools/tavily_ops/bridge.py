"""tools/tavily_ops/bridge.py — Async bridge + circuit breaker + retry.

v1.2 FIXES:
- Accept coroutine factory (callable) instead of coroutine object for retry.
- Use core/net/errors.py for unified retry classification.
- Always use ThreadPoolExecutor (removes fast path that breaks in pytest/event loops).
- Shorter default backoff to prevent worker pool exhaustion.
"""
from __future__ import annotations

import concurrent.futures
import time
import asyncio

from core.config import cfg
from core.net.errors import is_retryable_error, get_retry_delay
from tools.tavily_ops.client import _TAVILY_CB


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
            CORRECT:   _run_async_with_resilience(_call, trace_id=...)
            WRONG:     _run_async_with_resilience(_call(), trace_id=...)
        trace_id: Optional trace ID for observability.

    Returns:
        The coroutine's return value.

    Raises:
        Exception: If circuit breaker is OPEN or all retries are exhausted.
    """
    if not _TAVILY_CB.can_execute():
        raise Exception(
            "Tavily circuit breaker is OPEN — too many consecutive failures. "
            "Try again later or use web(search) as fallback."
        )

    last_exception = None
    for attempt in range(3):
        try:
            # v1.2 FIX: Create fresh coroutine from factory each attempt
            coro = coro_factory()
            result = _run_async(coro)
            _TAVILY_CB.record_success()
            return result
        except Exception as e:
            last_exception = e
            if is_retryable_error(e) and attempt < 2:
                # v1.2: Use unified backoff (shorter default: 2s base)
                backoff = get_retry_delay(attempt, base_delay=2.0, max_delay=10.0)
                time.sleep(backoff)
                continue
            _TAVILY_CB.record_failure()
            raise

    # Dead code — loop always returns or raises inside
    _TAVILY_CB.record_failure()
    raise last_exception
