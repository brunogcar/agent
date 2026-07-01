"""tests/tools/tavily/test_bridge_resilience.py — Retry with coroutine factory.

v1.2: Added to verify that _run_async_with_resilience correctly retries
using a fresh coroutine on each attempt. The v1.1 bug reused a single
coroutine object, causing RuntimeError on attempt 2.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import pytest

from tools.tavily_ops.bridge import _run_async_with_resilience


class TestBridgeResilience:
    """Test retry logic with coroutine factory pattern."""

    def test_factory_creates_fresh_coroutine_each_attempt(self):
        """Each retry must get a new coroutine from the factory."""
        call_count = [0]

        def factory():
            async def _coro():
                call_count[0] += 1
                if call_count[0] <= 2:
                    raise httpx.TimeoutException(f"fail #{call_count[0]}")
                return "success"
            return _coro()

        # Patch time.sleep to avoid real delays
        with patch("tools.tavily_ops.bridge.time.sleep"):
            result = _run_async_with_resilience(factory, trace_id="test")

        assert result == "success"
        assert call_count[0] == 3  # 2 failures + 1 success

    def test_retry_exhausted_raises_last_exception(self):
        """After max retries, the last exception is raised."""
        call_count = [0]

        def factory():
            async def _coro():
                call_count[0] += 1
                raise httpx.TimeoutException(f"fail #{call_count[0]}")
            return _coro()

        with patch("tools.tavily_ops.bridge.time.sleep"):
            with pytest.raises(httpx.TimeoutException, match="fail #3"):
                _run_async_with_resilience(factory, trace_id="test")

        assert call_count[0] == 3

    def test_success_on_first_attempt_no_retry(self):
        """If first attempt succeeds, no retries happen."""
        call_count = [0]

        def factory():
            async def _coro():
                call_count[0] += 1
                return "first_try"
            return _coro()

        result = _run_async_with_resilience(factory, trace_id="test")
        assert result == "first_try"
        assert call_count[0] == 1

    def test_circuit_breaker_open_raises_immediately(self):
        """When CB is open, factory is never called."""
        from tools.tavily_ops.client import _TAVILY_CB

        # Force CB open
        _TAVILY_CB._state = "open"
        _TAVILY_CB._last_failure_time = time.time()

        call_count = [0]

        def factory():
            async def _coro():
                call_count[0] += 1
                return "should not reach"
            return _coro()

        with pytest.raises(Exception, match="circuit breaker is OPEN"):
            _run_async_with_resilience(factory, trace_id="test")

        assert call_count[0] == 0  # Factory never called

        # Reset for other tests
        _TAVILY_CB.reset()

    def test_retry_uses_unified_backoff(self):
        """Retry uses get_retry_delay from core.net.errors."""
        call_count = [0]

        def factory():
            async def _coro():
                call_count[0] += 1
                if call_count[0] <= 2:
                    raise httpx.TimeoutException("retry me")
                return "ok"
            return _coro()

        with patch("tools.tavily_ops.bridge.time.sleep") as mock_sleep:
            with patch("tools.tavily_ops.bridge.get_retry_delay", return_value=2.5):
                result = _run_async_with_resilience(factory, trace_id="test")

        assert result == "ok"
        mock_sleep.assert_called_with(2.5)

    def test_non_retryable_error_no_retry(self):
        """Non-retryable errors (e.g., 404) fail immediately."""
        call_count = [0]

        def factory():
            async def _coro():
                call_count[0] += 1
                raise ValueError("not retryable")
            return _coro()

        # Patch is_retryable_error to return False for ValueError
        with patch("tools.tavily_ops.bridge.is_retryable_error", return_value=False):
            with pytest.raises(ValueError, match="not retryable"):
                _run_async_with_resilience(factory, trace_id="test")

        assert call_count[0] == 1  # No retry
