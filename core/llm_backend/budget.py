"""
core/llm_backend/budget.py - Rate limiting and budget protection.
"""
from __future__ import annotations
import time
import threading

class RateLimiter:
    """Thread-safe sliding window rate limiter."""
    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def is_allowed(self) -> bool:
        now = time.time()
        with self._lock:
            # Purge timestamps older than the period
            self._timestamps = [t for t in self._timestamps if now - t < self.period]
            if len(self._timestamps) < self.max_calls:
                self._timestamps.append(now)
                return True
            return False

# Global rate limiters for cloud providers (default: 5 calls per 60 seconds)
_provider_limiters: dict[str, RateLimiter] = {}

def check_rate_limit(provider: str, max_calls: int = 5, period: int = 60) -> bool:
    """Returns True if the call is allowed, False if rate limited."""
    if provider not in _provider_limiters:
        _provider_limiters[provider] = RateLimiter(max_calls, period)
    return _provider_limiters[provider].is_allowed()
