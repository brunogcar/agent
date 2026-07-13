"""core/llm_backend/circuit_breaker.py — Shared circuit breaker for LLM + tool resilience.

v1.2: Added reset() method for testability.
v1.3: Fixed record_failure() missing self._lock. Added _half_open_calls reset
      on HALF_OPEN → OPEN transition. Guarded _failure_count increment.
      FIXED: can_execute() now counts OPEN→HALF_OPEN transition against half_open_max_calls.


[DESIGN] KEY DECISIONS — read before modifying:

  1. GRANULARITY IS PER-ROLE, NOT PER-MODEL.
     LLMClient._breakers[role]. Key is "executor", not the model name.
     GET /health/circuit-breakers returns per-role keys; field is "failure_count".
     Response is null unless cfg.enable_metrics_endpoint is truthy.

  2. COOLDOWN IS DYNAMIC PER ROLE via recovery_timeout=role_cfg.timeout.
     Router's CB cools in 15s, planner's in 180s. Changing ROUTER_TIMEOUT in .env
     silently changes its CB cooldown.

  3. FAILURE COUNT NEVER DECAYS IN CLOSED STATE.
     record_success() is a NO-OP in CLOSED (only resets in HALF_OPEN).
     Three failures spread over days still trip the breaker.
     NOTE: retry_async_factory() in core/net/retry.py was fixed in v1.5 —
     on_failure now fires ONLY on final raise, not per retry attempt.
     This prevents transient retries from accumulating CB failure_count
     on overall-successful calls. Do NOT revert retry.py to per-attempt firing.

  4. HALF_OPEN: can_execute() counts the OPEN->HALF_OPEN probe call against
     half_open_max_calls. Confirmed empirically: 10 concurrent threads after
     cooldown -> exactly 1 gets True.
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
                    # v1.3 FIX: Fall through to HALF_OPEN check instead of returning True
                    # This ensures the transition call counts against half_open_max_calls
                else:
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
        """Record a failure and potentially open the circuit.

        v1.3 FIX: Now acquires self._lock for thread safety.
        v1.3 FIX: Resets _half_open_calls when transitioning from HALF_OPEN.
        v1.3 FIX: Only increments _failure_count when not already OPEN.
        """
        with self._lock:
            self._last_failure_time = time.time()

            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._half_open_calls = 0
                self._failure_count = self.failure_threshold
                return

            if self._state == self.OPEN:
                # Already open; just update timestamp. Don't increment count.
                return

            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
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
