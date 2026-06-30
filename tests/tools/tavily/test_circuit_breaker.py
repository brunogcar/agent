"""tests/tools/tavily/test_circuit_breaker.py — Circuit breaker integration tests.

v1.1: Added to verify the Tavily circuit breaker state machine:
CLOSED → OPEN → HALF_OPEN → CLOSED.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily_ops.client import _TAVILY_CB


class TestCircuitBreaker:
    """Test circuit breaker state transitions and integration."""

    def setup_method(self):
        """Reset CB to known state before each test."""
        _TAVILY_CB._state = "closed"
        _TAVILY_CB._failure_count = 0
        _TAVILY_CB._last_failure_time = 0.0
        _TAVILY_CB._half_open_calls = 0

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
