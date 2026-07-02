"""core/net/retry.py — Unified retry/backoff policies for all web tools.

v1.2: Extracted from bridge.py and web_ops/scrape.py.
v1.3: Added retry_async_factory() for async coroutine retry with circuit breaker hooks.
v1.4: Fixed on_failure called for non-retryable errors. Removed dead raise.
"""
from __future__ import annotations

import time
from typing import Callable, Any, Optional

from core.net.errors import is_retryable_error, get_retry_delay


def retry_sync(
    fn: Callable,
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    is_retryable: Callable[[Exception], bool] = is_retryable_error,
) -> Any:
    """Execute a synchronous function with retry on retryable errors.

    Args:
        fn: Function to call (synchronous).
        max_retries: Maximum number of retry attempts (not counting initial).
        base_delay: Initial backoff delay in seconds.
        max_delay: Maximum backoff cap.
        jitter: Add randomness to prevent thundering herd.
        is_retryable: Function to determine if an exception is retryable.

    Returns:
        The result of fn().

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exception = e
            if attempt < max_retries and is_retryable(e):
                delay = get_retry_delay(attempt, base_delay, max_delay, jitter)
                time.sleep(delay)
            else:
                raise


def retry_async_factory(
    coro_factory: Callable,
    *,
    run_async: Callable,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 10.0,
    jitter: bool = True,
    is_retryable: Callable[[Exception], bool] = is_retryable_error,
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
) -> Any:
    """Execute an async coroutine factory with retry and optional hooks.

    v1.3: Extracted from bridge.py _run_async_with_resilience for reuse
    across tools (tavily, web_ops, browser).
    v1.4: on_failure only fires for retryable errors; CB no longer tripped
    by validation failures or 4xx client errors.

    Args:
        coro_factory: Callable that returns a fresh coroutine each time.
        run_async: Function to run the coroutine (e.g., bridge._run_async).
        max_retries: Maximum retry attempts (not counting initial).
        base_delay: Initial backoff delay.
        max_delay: Maximum backoff cap.
        jitter: Add randomness to prevent thundering herd.
        is_retryable: Function to determine if an exception is retryable.
        on_success: Optional callback on success (e.g., CB.record_success).
        on_failure: Optional callback on each failure (e.g., CB.record_failure).

    Returns:
        The coroutine's return value.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            coro = coro_factory()
            result = run_async(coro)
            if on_success is not None:
                on_success()
            return result
        except Exception as e:
            last_exception = e
            if is_retryable(e):
                if on_failure is not None:
                    on_failure()
                if attempt < max_retries:
                    delay = get_retry_delay(attempt, base_delay, max_delay, jitter)
                    time.sleep(delay)
                else:
                    raise
            else:
                raise
