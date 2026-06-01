"""
core/llm_backend/budget.py - Rate limiting and budget protection.
"""
from __future__ import annotations
import time
import threading
from collections import deque

class ThreadSafeRateLimiter:
    """Thread-safe sliding window rate limiter using monotonic time."""
    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self._window = deque()
        self._lock = threading.Lock()

    def is_allowed(self) -> bool:
        now = time.monotonic()
        with self._lock:
            # Purge timestamps older than the period
            while self._window and now - self._window[0] > self.period:
                self._window.popleft()
            
            if len(self._window) < self.max_calls:
                self._window.append(now)
                return True
            return False

# Global rate limiters for cloud providers (default: 5 calls per 60 seconds)
_provider_limiters: dict[str, ThreadSafeRateLimiter] = {}
_limiters_lock = threading.Lock()

def check_rate_limit(provider: str, max_calls: int = 5, period: int = 60) -> bool:
    """Returns True if the call is allowed, False if rate limited."""
    with _limiters_lock:
        if provider not in _provider_limiters:
            _provider_limiters[provider] = ThreadSafeRateLimiter(max_calls, period)
        limiter = _provider_limiters[provider]
    
    return limiter.is_allowed()
