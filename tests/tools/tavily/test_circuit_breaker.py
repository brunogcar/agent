"""tests/tools/tavily/test_circuit_breaker.py — Circuit breaker integration tests.

v1.2: Added reset() method usage, half_open_max_calls enforcement test.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily_ops.client import _TAVILY_CB


class TestCircuitBreaker:
    """Test circuit breaker state transitions and integration."""

    def setup_method(self):
        """Reset CB to known state before each test."""
        _TAVILY_CB.reset()

    def test_initial_state_is_closed(self):
        assert _TAVILY_CB.get_state_info()["state"] == "closed"

    def test_can_execute_when_closed(self):
        assert _TAVILY_CB.can_execute() is True

    def test_opens_after_threshold_failures(self):
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()  # threshold = 3
        assert _TAVILY_CB.get_state_info()["state"] == "open"

    def test_fail_fast_when_open(self):
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()
        assert _TAVILY_CB.can_execute() is False

    def test_half_open_after_timeout(self):
        import time
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()
        # Simulate recovery timeout elapsed
        _TAVILY_CB._last_failure_time = time.time() - 70  # 60s timeout + buffer
        assert _TAVILY_CB.can_execute() is True
        assert _TAVILY_CB.get_state_info()["state"] == "half-open"

    def test_half_open_failure_reopens(self):
        _TAVILY_CB._state = "half-open"
        _TAVILY_CB.record_failure()
        assert _TAVILY_CB.get_state_info()["state"] == "open"

    def test_half_open_success_closes(self):
        _TAVILY_CB._state = "half-open"
        _TAVILY_CB.record_success()
        assert _TAVILY_CB.get_state_info()["state"] == "closed"
        assert _TAVILY_CB._failure_count == 0

    # v1.2: NEW — test half_open_max_calls enforcement
    def test_half_open_max_calls_enforced(self):
        """Only half_open_max_calls are allowed in HALF_OPEN state."""
        _TAVILY_CB._state = "half-open"
        _TAVILY_CB._half_open_calls = 0
        _TAVILY_CB.half_open_max_calls = 2

        assert _TAVILY_CB.can_execute() is True   # 1st call
        assert _TAVILY_CB.can_execute() is True   # 2nd call
        assert _TAVILY_CB.can_execute() is False  # 3rd call blocked

    # v1.2: NEW — test reset() method
    def test_reset_clears_all_state(self):
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()
        _TAVILY_CB.record_failure()
        assert _TAVILY_CB.get_state_info()["state"] == "open"

        _TAVILY_CB.reset()
        assert _TAVILY_CB.get_state_info()["state"] == "closed"
        assert _TAVILY_CB._failure_count == 0
        assert _TAVILY_CB._last_failure_time == 0.0
        assert _TAVILY_CB._half_open_calls == 0

    # v1.2: NEW — test record_success in CLOSED is no-op
    def test_record_success_in_closed_is_noop(self):
        _TAVILY_CB._state = "closed"
        _TAVILY_CB._failure_count = 2
        _TAVILY_CB.record_success()
        assert _TAVILY_CB._failure_count == 2  # Unchanged
        assert _TAVILY_CB.get_state_info()["state"] == "closed"
