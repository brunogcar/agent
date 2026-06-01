"""
core/llm_backend/circuit_breaker.py — Thread-safe circuit breaker pattern.

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
"""
from __future__ import annotations

import threading
import time
from typing import Any

class CircuitBreaker:
    """
    Thread-safe circuit breaker with state machine: CLOSED → OPEN → HALF_OPEN → CLOSED.
    
    States:
    - CLOSED:   Normal operation. Track failures.
    - OPEN:     Fail fast after threshold failures within timeout_seconds.
    - HALF_OPEN: After timeout, allow test calls to check if service recovered.
                 Success = CLOSED; Failure = OPEN again.
                 
    Fixed per DeepSeek analysis (2026-05-14) to enforce half_open_max_calls and proper
    transitions from HALF_OPEN → OPEN on failure. See references:
      - Circuit breaker pattern: https://oneuptime.com/blog/post/2026-01-23-python-circuit-breakers
      - Microsoft Learn: https://learn.microsoft.com/en-us/dotnet/architecture/microservices/implement-resilient-applications/use-httpclientfactory-to-implement-resilient-http-requests
    """
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60,
                 half_open_max_calls: int = 1) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = CircuitBreaker.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls: int = 0
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Enforces half_open_max_calls and proper state transitions."""
        now = time.time()
        with self._lock:
            if self._state == CircuitBreaker.CLOSED:
                return True

            if self._state == CircuitBreaker.OPEN:
                if now - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitBreaker.HALF_OPEN
                    self._half_open_calls = 0
                else:
                    return False

            if self._state == CircuitBreaker.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                else:
                    return False
        
        return False

    def record_success(self) -> None:
        """Reset on successful call (probing succeeded)."""
        with self._lock:
            if self._state == CircuitBreaker.HALF_OPEN:
                self._state = CircuitBreaker.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0

    def record_failure(self) -> None:
        """Failures in HALF_OPEN immediately reopen the circuit!"""
        now = time.time()
        with self._lock:
            if self._state == CircuitBreaker.HALF_OPEN:
                # Probing failed – go back to open immediately
                self._state = CircuitBreaker.OPEN
                self._failure_count = self.failure_threshold
                self._half_open_calls = 0
            elif self._state == CircuitBreaker.CLOSED:
                self._failure_count += 1
                self._last_failure_time = now
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitBreaker.OPEN

    def get_state_info(self) -> dict[str, Any]:
        """Return circuit breaker state info for monitoring."""
        with self._lock:
            time_since_failure = 0.0
            if self._last_failure_time > 0:
                time_since_failure = time.time() - self._last_failure_time
            return {
                "state": self._state,
                "failure_count": self._failure_count,
                "timeout_seconds": self.recovery_timeout,
                "time_since_last_failure": time_since_failure,
            }