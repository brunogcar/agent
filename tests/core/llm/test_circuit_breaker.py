"""Unit tests for CircuitBreaker state machine."""
from __future__ import annotations

import time
import pytest
from core.llm_backend.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        """Circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        assert breaker.can_execute() is True
        state = breaker.get_state_info()
        assert state["state"] == "closed"
        assert state["failure_count"] == 0

    def test_opens_after_threshold_failures(self):
        """Circuit opens after consecutive failures."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.can_execute() is True
        breaker.record_failure()  # 3rd failure
        assert breaker.can_execute() is False
        state = breaker.get_state_info()
        assert state["state"] == "open"
        assert state["failure_count"] == 3

    def test_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.can_execute() is False
        breaker._last_failure_time = time.time() - 2  # 2 seconds ago
        assert breaker.can_execute() is True
        state = breaker.get_state_info()
        assert state["state"] == "half-open"

    def test_closes_on_success_in_half_open(self):
        """Successful call in HALF_OPEN closes the circuit."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        breaker._last_failure_time = time.time() - 2
        breaker.can_execute()  # Transitions to HALF_OPEN
        breaker.record_success()
        state = breaker.get_state_info()
        assert state["state"] == "closed"
        assert state["failure_count"] == 0

    def test_reopens_on_failure_in_half_open(self):
        """Failed call in HALF_OPEN reopens the circuit."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        breaker._last_failure_time = time.time() - 2
        breaker.can_execute()  # Transitions to HALF_OPEN
        breaker.record_failure()
        state = breaker.get_state_info()
        assert state["state"] == "open"
        assert state["failure_count"] == breaker.failure_threshold
