"""Response cache for deterministic agent roles.

Deterministic roles (classify, route) are cached to eliminate redundant LLM calls.
The cache is keyed by SHA256 hash of role:task:context:content, with a 5-minute TTL
and 100-entry LRU eviction.

This module is stateful at the process level. Tests must call _clear_cache()
in setup_method to avoid cross-test contamination.
"""
from __future__ import annotations

import hashlib as _hashlib
import time as _time

from core.config import cfg

# Module-level cache storage — keyed by 16-char SHA256 prefix.
# Value is a tuple of (response_dict, timestamp_float).
_CACHE: dict[str, tuple[dict, float]] = {}

# [Bug #19] Cache limits now read from cfg (was hardcoded 100 / 300).
# Read at module load for fast access; cfg is a singleton initialized
# before this module imports. If cfg isn't ready, fall back to defaults.
try:
    _CACHE_MAX = cfg.agent_cache_max
    _CACHE_TTL_SECONDS = cfg.agent_cache_ttl_seconds
except AttributeError:
    _CACHE_MAX = 100
    _CACHE_TTL_SECONDS = 300


def _cache_key(role: str, task: str, context: str, content: str, temperature: float = -1.0, max_tokens: int = -1, model: str = "") -> str:
    """Build a deterministic cache key from the agent call parameters.

    Uses SHA256 truncated to 16 hex chars for fast comparison while
    keeping collision probability negligible for 100-entry cache.
    Includes temperature and max_tokens when they are non-default values
    to prevent cache hits with different generation parameters.

    [Bug #23] Now includes the model name when provided. This prevents
    stale cache hits when the same role uses different models (e.g.,
    during benchmark overrides or model swaps). Backward compatible —
    callers that don't pass `model` get the old behavior.
    """
    raw = f"{role}:{task}:{context}:{content}"
    if model:
        raw += f":mdl={model}"
    if temperature >= 0:
        raw += f":t={temperature}"
    if max_tokens > 0:
        raw += f":m={max_tokens}"
    return _hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_cached(key: str) -> dict | None:
    """Return the cached response if it exists and has not expired.

    On TTL expiry, the entry is deleted from _CACHE and None is returned.
    The returned dict is a reference to the stored object — callers that
    mutate it will corrupt the cache. Use .copy() if mutation is needed.
    """
    if key not in _CACHE:
        return None
    response, timestamp = _CACHE[key]
    if _time.time() - timestamp > _CACHE_TTL_SECONDS:
        del _CACHE[key]
        return None
    return response


def _set_cached(key: str, response: dict) -> None:
    """Store a response in the cache with the current timestamp.

    If the cache exceeds _CACHE_MAX entries, the oldest entry (by
    timestamp) is evicted via LRU logic.
    """
    _CACHE[key] = (response, _time.time())
    while len(_CACHE) > _CACHE_MAX:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][1])
        del _CACHE[oldest]


def _clear_cache() -> None:
    """Clear all cached responses. Primarily for testing isolation."""
    _CACHE.clear()
