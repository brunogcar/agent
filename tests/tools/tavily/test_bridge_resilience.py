"""Tests for tools/tavily_ops/bridge.py — resilience, retry, circuit breaker.

v1.3: Fixed retry count (max_retries=2 means 3 total attempts: initial + 2 retries).
      Fixed backoff patch target (core.net.retry.time.sleep, not bridge.time.sleep).
      FIXED: test_retry_exhausted_raises matches bridge's max_retries=3 (4 attempts).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from tools.tavily_ops import bridge
from tools.tavily_ops.client import _TAVILY_CB


class TestBridgeResilience:
    """Tests for _run_async_with_resilience retry and circuit breaker integration."""

    def setup_method(self):
        """Reset circuit breaker before each test."""
        _TAVILY_CB.reset()

    def test_factory_creates_fresh_coroutine_each_attempt(self):
        """Factory must create a new coroutine on each retry attempt."""
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def _coro():
                if call_count[0] < 3:
                    raise httpx.TimeoutException(f"attempt {call_count[0]}")
                return {"ok": True}
            return _coro()

        with patch("core.net.retry.time.sleep"):
            result = bridge._run_async_with_resilience(factory, trace_id="test")
            assert result == {"ok": True}
            assert call_count[0] == 3

    def test_retry_exhausted_raises_last_exception(self):
        """After max_retries exhausted, raise the last exception.

        v1.3 FIX: bridge._run_async_with_resilience passes max_retries=3 to
        retry_async_factory, so there are 4 total attempts (initial + 3 retries).
        The last error message is 'fail #4'.
        """
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def _coro():
                raise httpx.TimeoutException(f"fail #{call_count[0]}")
            return _coro()

        with patch("core.net.retry.time.sleep"):
            with pytest.raises(httpx.TimeoutException, match="fail #4"):
                bridge._run_async_with_resilience(factory, trace_id="test")
            assert call_count[0] == 4  # initial + 3 retries

    def test_success_on_first_attempt_no_retry(self):
        """No retry when first attempt succeeds."""
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def _coro():
                return {"status": "ok"}
            return _coro()

        result = bridge._run_async_with_resilience(factory, trace_id="test")
        assert result == {"status": "ok"}
        assert call_count[0] == 1

    def test_circuit_breaker_open_raises_immediately(self):
        """CB OPEN blocks before calling factory."""
        factory = MagicMock()
        _TAVILY_CB._state = "open"
        _TAVILY_CB._last_failure_time = __import__("time").time()

        with pytest.raises(bridge.CircuitBreakerOpen):
            bridge._run_async_with_resilience(factory, trace_id="test")
        factory.assert_not_called()

        _TAVILY_CB.reset()

    def test_retry_uses_unified_backoff(self):
        """Retry uses get_retry_delay from core.net.errors.

        v1.3 FIX: Patch core.net.retry.time.sleep (not bridge.time.sleep).
        """
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def _coro():
                if call_count[0] < 2:
                    raise httpx.TimeoutException("transient")
                return {"ok": True}
            return _coro()

        with patch("core.net.retry.time.sleep") as mock_sleep:
            bridge._run_async_with_resilience(factory, trace_id="test")

            # Should sleep once (after first failure, before second attempt)
            assert mock_sleep.call_count == 1
            # Verify sleep was called with a positive delay
            delay = mock_sleep.call_args[0][0]
            assert delay > 0

    def test_non_retryable_error_no_retry(self):
        """Non-retryable errors fail immediately."""
        call_count = [0]

        def factory():
            call_count[0] += 1
            async def _coro():
                raise ValueError("not retryable")
            return _coro()

        with pytest.raises(ValueError, match="not retryable"):
            bridge._run_async_with_resilience(factory, trace_id="test")
        assert call_count[0] == 1
