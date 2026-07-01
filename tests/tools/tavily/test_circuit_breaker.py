"""Tests for tools/tavily_ops/client.py circuit breaker integration.

v1.3: Fixed threshold from 3 to 5 (matches new default).
      Uses public methods to reach desired state instead of direct mutation.
      FIXED: test_half_open_max_calls_enforced now accounts for OPEN->HALF_OPEN
      transition counting against half_open_max_calls.
"""
from __future__ import annotations

import time

import pytest

from tools.tavily_ops.client import _TAVILY_CB


class TestCircuitBreaker:
    """Tests for the Tavily circuit breaker."""

    def setup_method(self):
        """Reset CB before each test."""
        _TAVILY_CB.reset()

    def test_opens_after_threshold_failures(self):
        """CB opens after failure_threshold consecutive failures.

        v1.3 FIX: threshold is 5, not 3.
        """
        for _ in range(5):
            _TAVILY_CB.record_failure()
        assert _TAVILY_CB.get_state_info()["state"] == "open"

    def test_fail_fast_when_open(self):
        """CB rejects calls when OPEN."""
        for _ in range(5):
            _TAVILY_CB.record_failure()
        assert _TAVILY_CB.can_execute() is False

    def test_half_open_after_timeout(self):
        """CB transitions to HALF_OPEN after recovery timeout."""
        for _ in range(5):
            _TAVILY_CB.record_failure()
        assert _TAVILY_CB.get_state_info()["state"] == "open"

        # Simulate timeout
        _TAVILY_CB._last_failure_time = time.time() - 70
        assert _TAVILY_CB.can_execute() is True
        assert _TAVILY_CB.get_state_info()["state"] == "half-open"

    def test_half_open_success_closes(self):
        """Success in HALF_OPEN closes the circuit."""
        for _ in range(5):
            _TAVILY_CB.record_failure()
        _TAVILY_CB._last_failure_time = time.time() - 70
        _TAVILY_CB.can_execute()  # Transition to HALF_OPEN
        _TAVILY_CB.record_success()
        assert _TAVILY_CB.get_state_info()["state"] == "closed"

    def test_half_open_failure_reopens(self):
        """Failure in HALF_OPEN reopens the circuit."""
        for _ in range(5):
            _TAVILY_CB.record_failure()
        _TAVILY_CB._last_failure_time = time.time() - 70
        _TAVILY_CB.can_execute()  # Transition to HALF_OPEN
        _TAVILY_CB.record_failure()
        assert _TAVILY_CB.get_state_info()["state"] == "open"

    def test_half_open_max_calls_enforced(self):
        """Only half_open_max_calls allowed in HALF_OPEN.

        v1.3 FIX: The OPEN->HALF_OPEN transition itself counts as the first
        HALF_OPEN call (can_execute increments _half_open_calls after transition).
        With half_open_max_calls=1, the first call consumes the quota.
        """
        for _ in range(5):
            _TAVILY_CB.record_failure()
        _TAVILY_CB._last_failure_time = time.time() - 70
        # First call: transitions OPEN->HALF_OPEN, then HALF_OPEN check
        # increments _half_open_calls to 1 and returns True
        assert _TAVILY_CB.can_execute() is True
        # Second call: _half_open_calls=1 which is NOT < 1, returns False
        assert _TAVILY_CB.can_execute() is False  # Exceeded max

    def test_reset_clears_all_state(self):
        """reset() clears all state."""
        for _ in range(5):
            _TAVILY_CB.record_failure()
        assert _TAVILY_CB.get_state_info()["state"] == "open"
        _TAVILY_CB.reset()
        assert _TAVILY_CB.get_state_info()["state"] == "closed"
        assert _TAVILY_CB.get_state_info()["failure_count"] == 0

    def test_record_success_in_closed_is_noop(self):
        """Success in CLOSED state is a no-op."""
        _TAVILY_CB.record_success()
        assert _TAVILY_CB.get_state_info()["state"] == "closed"
        assert _TAVILY_CB.get_state_info()["failure_count"] == 0
