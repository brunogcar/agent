"""core/net/retry.py — Unified retry/backoff policies for all web tools.

v1.2: Extracted from bridge.py and web_ops/scrape.py.
v1.3: Added retry_async_factory() for async coroutine retry with circuit breaker hooks.
v1.4: Fixed on_failure called for non-retryable errors. Removed dead raise.
v1.5: Fixed on_failure accumulating per-retry-attempt on retryable errors.
      Now fires only on final raise (retry exhaustion), preserving v1.4 semantics
      (non-retryable errors still don't trip CB). Prevents CB from opening on
      successful-but-retried calls.
v1.6: Switched time.sleep → _sleep (module-level reference). Tests now patch
      core.net.retry._sleep instead of core.net.retry.time.sleep. The old
      patch target was global (time is a singleton module) so ANY background
      thread calling time.sleep during a test hit the mock — causing
      assert_called_once() to fail with thousands of stray calls.
"""
from __future__ import annotations

import time
from typing import Callable, Any, Optional

# v1.6: Module-level sleep reference so tests can patch core.net.retry._sleep
# without globally mocking time.sleep (which catches stray calls from
# background threads like the browser reaper or watchdog).
_sleep = time.sleep

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
                _sleep(delay)
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
    v1.5: on_failure only fires on final raise (retry exhaustion), not per
    retry attempt. Prevents CB failure_count from accumulating on
    successful-but-retried calls.

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
            # Retryable errors: retry if attempts remain, otherwise fall through to raise.
            if is_retryable(e) and attempt < max_retries:
                delay = get_retry_delay(attempt, base_delay, max_delay, jitter)
                _sleep(delay)
                continue
            # Final raise — either retries exhausted (retryable) or non-retryable error.
            #
            # [DESIGN] on_failure is called ONLY on final raise, not per retry attempt.
            # Calling it per-attempt means transient failures accumulate CB failure_count
            # even on overall successful calls (3 calls × 2 retries = 6 record_failure()
            # calls → CB opens despite every call succeeding). record_success() is a no-op
            # in CLOSED CB state by design, so interim failures never cancel out.
            # DO NOT move this back inside the per-attempt loop.
            #
            # [v1.4 SEMANTICS] on_failure only fires for retryable errors. Non-retryable
            # errors (validation, 4xx) raise immediately without tripping the CB.
            if is_retryable(e) and on_failure is not None:
                on_failure()
            raise
