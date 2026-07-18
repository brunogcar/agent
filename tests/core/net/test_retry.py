"""Tests for core/net/retry.py — unified retry/backoff policies.

v1.3: Fixed to use httpx.ConnectError instead of stdlib ConnectionError.
      Added test for retry_async_factory.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.net.retry import retry_sync, retry_async_factory
from core.net.errors import get_retry_delay


class TestRetrySync:
    """Tests for retry_sync() synchronous retry wrapper."""

    def test_success_without_retry(self):
        """Function succeeds on first attempt — no retry needed."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            return "ok"

        result = retry_sync(fn, max_retries=3)
        assert result == "ok"
        assert call_count[0] == 1

    def test_retry_on_retryable_error(self):
        """Retry on retryable error (httpx.ConnectError) — 3 attempts total."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise httpx.ConnectError("transient")
            return "ok"

        with patch("core.net.retry._sleep"):
            result = retry_sync(fn, max_retries=3)
            assert result == "ok"
            assert call_count[0] == 3

    def test_exhaust_retries_raises(self):
        """All retries exhausted — raises last exception."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise httpx.ConnectError("always fails")

        with patch("core.net.retry._sleep"):
            with pytest.raises(httpx.ConnectError, match="always fails"):
                retry_sync(fn, max_retries=2)
            assert call_count[0] == 3  # initial + 2 retries

    def test_no_retry_on_non_retryable(self):
        """Non-retryable error fails immediately."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            retry_sync(fn, max_retries=3)
        assert call_count[0] == 1

    def test_custom_is_retryable(self):
        """Custom retry predicate works."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("maybe retryable")
            return "ok"

        def custom_retry(e):
            return isinstance(e, RuntimeError)

        with patch("core.net.retry._sleep"):
            result = retry_sync(fn, max_retries=3, is_retryable=custom_retry)
            assert result == "ok"
            assert call_count[0] == 2

    def test_backoff_delays(self):
        """Backoff delays follow exponential progression."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise httpx.ConnectError("transient")
            return "ok"

        sleeps = []

        def capture_sleep(duration):
            sleeps.append(duration)

        with patch("core.net.retry._sleep", side_effect=capture_sleep):
            retry_sync(fn, max_retries=3, base_delay=1.0, jitter=False)

        # Delays: 1.0 * 2^0 = 1.0, 1.0 * 2^1 = 2.0
        assert len(sleeps) == 2
        assert sleeps[0] == pytest.approx(1.0, rel=0.01)
        assert sleeps[1] == pytest.approx(2.0, rel=0.01)

    def test_jitter_range(self):
        """Jitter adds 0-25% randomness to delay."""
        for _ in range(20):
            # v1.3 FIX: Use get_retry_delay from core.net.errors, not retry_sync._get_retry_delay
            delay = get_retry_delay(0, base_delay=2.0, jitter=True)
            assert 2.0 <= delay <= 2.5


class TestRetryAsyncFactory:
    """Tests for retry_async_factory() — async coroutine retry with hooks."""

    def test_success_no_retry(self):
        """Async factory succeeds on first attempt."""
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def coro():
                return "ok"
            return coro()

        def run_async(coro):
            import asyncio
            return asyncio.run(coro)

        result = retry_async_factory(
            factory,
            run_async=run_async,
            max_retries=2,
        )
        assert result == "ok"
        assert call_count[0] == 1

    def test_retry_exhausted_raises(self):
        """All retries exhausted — raises last exception."""
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def coro():
                raise httpx.TimeoutException(f"fail #{call_count[0]}")
            return coro()

        def run_async(coro):
            import asyncio
            return asyncio.run(coro)

        with patch("core.net.retry._sleep"):
            with pytest.raises(httpx.TimeoutException, match="fail #3"):
                retry_async_factory(
                    factory,
                    run_async=run_async,
                    max_retries=2,
                )
            assert call_count[0] == 3  # initial + 2 retries

    def test_cb_hooks_called(self):
        """Circuit breaker hooks are called on success/failure."""
        successes = []
        failures = []

        def factory():
            async def coro():
                return "ok"
            return coro()

        def run_async(coro):
            import asyncio
            return asyncio.run(coro)

        retry_async_factory(
            factory,
            run_async=run_async,
            on_success=lambda: successes.append(1),
            on_failure=lambda: failures.append(1),
        )
        assert len(successes) == 1
        assert len(failures) == 0

    def test_on_failure_not_called_on_retried_success(self):
        """v1.5 regression: on_failure must NOT fire on retry attempts that
        eventually succeed.

        Previously on_failure was called per-attempt, so a call that needed
        2 retries to succeed would record 2 failures permanently. Three such
        calls would open the CB despite every call succeeding overall.
        record_success() is a no-op in CLOSED CB state, so interim failures
        never cancel out.
        """
        successes = []
        failures = []
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def coro():
                # Fail twice, then succeed on the 3rd attempt.
                if call_count[0] < 3:
                    raise httpx.TimeoutException(f"transient #{call_count[0]}")
                return "ok"
            return coro()

        def run_async(coro):
            import asyncio
            return asyncio.run(coro)

        result = retry_async_factory(
            factory,
            run_async=run_async,
            max_retries=3,
            on_success=lambda: successes.append(1),
            on_failure=lambda: failures.append(1),
        )

        assert result == "ok"
        assert call_count[0] == 3  # initial + 2 retries
        assert len(successes) == 1
        assert len(failures) == 0, (
            f"on_failure must NOT fire on per-attempt retries that succeed overall; "
            f"got {len(failures)} failure callbacks. This regresses the v1.5 CB fix."
        )

    def test_on_failure_called_once_on_retry_exhaustion(self):
        """v1.5 regression: on_failure fires exactly once when retries are
        exhausted, not once per attempt."""
        failures = []
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def coro():
                raise httpx.TimeoutException(f"fail #{call_count[0]}")
            return coro()

        def run_async(coro):
            import asyncio
            return asyncio.run(coro)

        with patch("core.net.retry._sleep"):
            with pytest.raises(httpx.TimeoutException):
                retry_async_factory(
                    factory,
                    run_async=run_async,
                    max_retries=2,
                    on_failure=lambda: failures.append(1),
                )

        assert call_count[0] == 3  # initial + 2 retries
        assert len(failures) == 1, (
            f"on_failure must fire exactly once on retry exhaustion, not per attempt; "
            f"got {len(failures)} callbacks."
        )

    def test_on_failure_not_called_on_non_retryable(self):
        """v1.4 semantics preserved: non-retryable errors raise immediately
        without tripping the CB."""
        failures = []

        def factory():
            async def coro():
                raise ValueError("non-retryable validation error")
            return coro()

        def run_async(coro):
            import asyncio
            return asyncio.run(coro)

        with pytest.raises(ValueError):
            retry_async_factory(
                factory,
                run_async=run_async,
                max_retries=3,
                on_failure=lambda: failures.append(1),
            )

        assert len(failures) == 0, (
            "on_failure must NOT fire for non-retryable errors (v1.4 semantics)."
        )
