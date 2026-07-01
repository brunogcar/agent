"""core/llm_backend/circuit_breaker.py — Shared circuit breaker for LLM + tool resilience.

v1.2: Added reset() method for testability.
"""
from __future__ import annotations

import time
import threading


class CircuitBreaker:
    """Thread-safe circuit breaker with half-open probing."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self._state == self.CLOSED:
                return True
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    self._half_open_calls = 0
                    return True
                return False
            if self._state == self.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state == self.HALF_OPEN:
                self._state = self.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
            # In CLOSED state, success is a no-op (we don't track success count)

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
            elif self._failure_count >= self.failure_threshold:
                self._state = self.OPEN

    def get_state_info(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "failure_count": self._failure_count,
                "last_failure_time": self._last_failure_time,
                "half_open_calls": self._half_open_calls,
            }

    # v1.2: NEW — reset() method for testability
    def reset(self) -> None:
        """Reset circuit breaker to CLOSED state. Useful for tests."""
        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0
            self._half_open_calls = 0
