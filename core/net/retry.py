"""core/net/retry.py — Unified retry/backoff policies for all web tools.

v1.2: Extracted from bridge.py and web_ops/scrape.py.
"""
from __future__ import annotations

import time
from typing import Callable, Any

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
    raise last_exception
