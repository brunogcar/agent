"""
core/llm_backend/budget.py - Rate limiting, token budgeting, and observability helpers.
"""
from __future__ import annotations
import time
import threading
from collections import deque
from typing import Tuple, List

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
            while self._window and now - self._window[0] > self.period:
                self._window.popleft()
            if len(self._window) < self.max_calls:
                self._window.append(now)
                return True
            return False

_provider_limiters: dict[str, ThreadSafeRateLimiter] = {}
_limiters_lock = threading.Lock()

def check_rate_limit(provider: str, max_calls: int = 5, period: int = 60) -> bool:
    """Returns True if the call is allowed, False if rate limited."""
    with _limiters_lock:
        if provider not in _provider_limiters:
            _provider_limiters[provider] = ThreadSafeRateLimiter(max_calls, period)
        limiter = _provider_limiters[provider]
    return limiter.is_allowed()

# -- Phase 5A & 5B: Token Budgeting & Cost Estimation ----------------------
_PROVIDER_COST_PER_1K_TOKENS = {
    "openai": 0.005,    # GPT-4o mini approx
    "deepseek": 0.0002, # DeepSeek Chat approx
    "mistral": 0.0005,  # Mistral Large approx
    "qwen": 0.0005,
    "kimi": 0.001,
    "lmstudio": 0.0,
}

def estimate_cost(provider: str, total_tokens: int) -> float:
    """Estimate cost in USD based on provider and total tokens."""
    rate = _PROVIDER_COST_PER_1K_TOKENS.get(provider.lower(), 0.001)
    return (total_tokens / 1000.0) * rate

def truncate_by_tokens(text: str, max_tokens: int) -> Tuple[str, bool, int]:
    """Truncate text to fit within max_tokens. Returns (truncated_text, was_truncated, estimated_tokens)."""
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        tokens = encoder.encode(text)
        estimated = len(tokens)
        if estimated > max_tokens:
            return encoder.decode(tokens[:max_tokens]), True, max_tokens
        return text, False, estimated
    except ImportError:
        # Fallback: ~4 chars per token
        estimated = len(text) // 4
        if estimated > max_tokens:
            char_limit = max_tokens * 4
            return text[:char_limit], True, max_tokens
        return text, False, estimated

def enforce_global_context_budget(system: str, context: str, user: str, content: str, max_tokens: int) -> Tuple[str, str, List[str]]:
    """Phase 5A: Enforce global context budget before sending to LLM."""
    warnings = []
    reserved = (len(system) + len(user)) // 4
    available_for_context = max(500, max_tokens - reserved)
    
    if context:
        ctx, was_trunc, _ = truncate_by_tokens(context, available_for_context // 2)
        if was_trunc: warnings.append(f"Context truncated to respect global budget of {max_tokens} tokens.")
        context = ctx
        
    if content:
        cont, was_trunc, _ = truncate_by_tokens(content, available_for_context // 2)
        if was_trunc: warnings.append(f"Content truncated to respect global budget of {max_tokens} tokens.")
        content = cont
        
    return context, content, warnings
