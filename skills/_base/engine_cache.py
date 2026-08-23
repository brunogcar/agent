"""skills/_base/engine_cache.py — ContextVar-scoped per-call engine cache.

Provides:
  - _ENGINE_CACHE ContextVar (the cache slot)
  - engine_cached() decorator (3-layer: in-memory cache + DB cache + real fn)
  - engine_cache_scope context manager (activates the cache for its block)

Eliminates redundant DB queries when multiple metrics compose the same
engine within a single compute_all_ratios() call.

Part of the skills/_base/ package split (was originally in skills/_base.py).
"""
from __future__ import annotations

import functools
from contextvars import ContextVar
from typing import Callable


# ── F7: Engine cache (ContextVar-scoped per-call cache) ─────────────────────
#
# Eliminates redundant DB queries when multiple metrics compose the same
# engine within a single compute_all_ratios() call.
#
# Example: ROE, ROIC, sustainable_growth, LPA, DPA all call earnings_at().
# Without the cache, earnings_at() fires 5 DB queries for the same value.
# With the cache, it fires 1 query + 4 cache hits.
#
# HOW IT WORKS:
#   - `@engine_cached` decorator is applied to each engine's at_fn +
#     periods_fn at module definition time (before any metric imports them).
#   - The decorator checks `_ENGINE_CACHE` ContextVar; if None (no scope
#     active), it's a passthrough (zero overhead for standalone calls).
#   - `compute_all_ratios()` wraps its loop in `with engine_cache_scope():`
#     to activate the cache for the duration of the call.
#
# WHY DECORATOR (not monkey-patch):
#   - Metrics use `from engines.earnings import ttm_earnings_at` — a direct
#     reference bound at import time. Monkey-patching the module attribute
#     after import is INVISIBLE to metrics (they hold the original ref).
#   - The decorator is applied at definition time, BEFORE any import binds
#     the name. So `spec.at_fn` and `module.fn` are the SAME wrapper object,
#     permanently. No restore, no race, no test changes.
#
# THREAD SAFETY:
#   ContextVar is per-thread + per-asyncio-task. Two concurrent
#   compute_all_ratios() calls each get their own cache dict. No lock needed.
#
# REENTRANCY:
#   If compute_all_ratios() is called nested (e.g., valuation calls financials
#   which calls compute_all_ratios), the inner call reuses the outer scope's
#   cache instead of wiping it. See engine_cache_scope.__enter__.

_ENGINE_CACHE: ContextVar[dict | None] = ContextVar(
    "_engine_cache", default=None,
)


def engine_cached(fn: Callable) -> Callable:
    """Decorator that caches an engine function's results within a scope.

    Apply to engine `at_fn(company, date)` and `periods_fn(company)` at
    module definition time. When no cache scope is active, the wrapper is
    a passthrough (zero overhead).

    [v2.2] The decorator now has 3 layers:
      1. In-memory cache (ContextVar — within one engine_cache_scope)
      2. DB cache (persistent — cross-skill, cross-process)
      3. Real engine fn (queries DFP/ITR/COTAHIST/SGS)

    The DB cache (data_sources._cache) persists engine results across
    route() calls so that when valuation computes revenue_at("PETR4",
    "2024-06-30") and then financials computes the same, the second call
    is a DB cache hit. Invalidation is per-company via a fingerprint
    (MAX(versao) + MAX(data_fim_exerc) for DFP/ITR, MAX(refdate) for
    COTAHIST, etc.) — see data_sources/_cache.py for details.

    Cache keys:
      - at_fn:      (fn.__name__, company, str(date))
      - periods_fn: (fn.__name__, company, "__periods__")

    None values ARE cached in-memory (prevents re-querying within one run)
    but are NOT stored in the DB cache (prevents stale Nones across runs).
    See data_sources/_cache.py:get_cached + set_cached for the DB-layer fix.

    Usage in engines/earnings.py:
        from skills._base import engine_cached

        @engine_cached
        def ttm_earnings_at(company, date):
            ...

        @engine_cached
        def ttm_earnings_periods(company):
            ...

    The decorator uses functools.wraps to preserve __name__, __module__,
    __wrapped__, and __doc__ — so `spec.at_fn is module.fn` remains True
    (both point to the wrapper) and introspection works normally.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        cache = _ENGINE_CACHE.get()

        # Build cache key from function name + positional args.
        # at_fn(company, date) → (fn_name, company, date)
        # periods_fn(company) → (fn_name, company) — no date arg
        # periods_fn(company, date_from, date_to) → (fn_name, company, date_from, date_to)
        key = (fn.__name__,) + tuple(str(a) for a in args)

        # Layer 1: In-memory cache (within one engine_cache_scope)
        if cache is not None:
            if key in cache:
                cache["_hits"] = cache.get("_hits", 0) + 1
                return cache[key]

        # Layer 2: DB cache (persistent, cross-skill)
        if len(args) >= 2:
            # at_fn has (company, date) → use engine_cache table (REAL values)
            # Check: is this an at_fn or a multi-arg periods_fn?
            # at_fn returns float|None, periods_fn returns list|dict.
            # Heuristic: if the function name ends with "_at", it's an at_fn.
            # Otherwise, if len(args) > 2, it's a multi-arg periods_fn.
            if fn.__name__.endswith("_at") or (len(args) == 2 and not fn.__name__.endswith("_periods")):
                # at_fn → engine_cache table
                try:
                    from data_sources._cache import is_valid, get_cached, set_cached
                    company = str(args[0])
                    date = str(args[1])
                    if is_valid(fn.__name__, company):
                        db_cached = get_cached(fn.__name__, company, date)
                        if db_cached is not None:
                            if cache is not None:
                                cache[key] = db_cached["value"]
                                cache["_db_hits"] = cache.get("_db_hits", 0) + 1
                            return db_cached["value"]
                except Exception:
                    pass
            else:
                # Multi-arg periods_fn (e.g., price_series(ticker, date_from, date_to))
                # → use engine_periods table with args_suffix
                try:
                    from data_sources._cache import is_valid, get_cached_periods, set_cached_periods
                    company = str(args[0])
                    args_suffix = "_".join(str(a) for a in args[1:])
                    if is_valid(fn.__name__, company):
                        db_periods = get_cached_periods(fn.__name__, company, args_suffix)
                        if db_periods is not None:
                            if cache is not None:
                                cache[key] = db_periods
                                cache["_db_hits"] = cache.get("_db_hits", 0) + 1
                            return db_periods
                except Exception:
                    pass
        elif len(args) == 1:
            # periods_fn has (company) → use engine_periods table (JSON values)
            try:
                from data_sources._cache import is_valid, get_cached_periods, set_cached_periods
                company = str(args[0])
                if is_valid(fn.__name__, company):
                    db_periods = get_cached_periods(fn.__name__, company)
                    if db_periods is not None:
                        if cache is not None:
                            cache[key] = db_periods
                            cache["_db_hits"] = cache.get("_db_hits", 0) + 1
                        return db_periods
            except Exception:
                pass

        # Layer 3: Real engine function
        if cache is not None:
            cache["_misses"] = cache.get("_misses", 0) + 1
        result = fn(*args, **kwargs)

        # Write to in-memory cache
        if cache is not None:
            cache[key] = result

        # Write to DB cache
        if len(args) >= 2:
            if fn.__name__.endswith("_at") or (len(args) == 2 and not fn.__name__.endswith("_periods")):
                # at_fn → engine_cache table (REAL value)
                try:
                    from data_sources._cache import set_cached
                    company = str(args[0])
                    date = str(args[1])
                    set_cached(fn.__name__, company, date, result)
                except Exception:
                    pass
            else:
                # Multi-arg periods_fn → engine_periods table with args_suffix
                try:
                    from data_sources._cache import set_cached_periods
                    company = str(args[0])
                    args_suffix = "_".join(str(a) for a in args[1:])
                    set_cached_periods(fn.__name__, company, result, args_suffix)
                except Exception:
                    pass
        elif len(args) == 1:
            # periods_fn → engine_periods table (JSON-serialized list)
            try:
                from data_sources._cache import set_cached_periods
                company = str(args[0])
                set_cached_periods(fn.__name__, company, result)
            except Exception:
                pass

        return result
    return wrapper


class engine_cache_scope:
    """Context manager that activates the engine cache for its block.

    Usage:
        with engine_cache_scope():
            result = compute_all_ratios("PETR4", "2024-06-30")

    Within the block, every `@engine_cached` function with the same args
    returns the cached value instead of re-querying the DB. The cache is
    dropped when the block exits.

    REENTRANCY: If a scope is already active (nested compute_all_ratios
    call), the inner call reuses the outer scope's cache instead of
    installing a new one. This prevents the inner call's `__exit__` from
    wiping the outer call's cache mid-flight.

    Thread-safety: ContextVar is async-safe + thread-safe (each context
    gets its own value). No cross-thread leakage.
    """

    def __init__(self) -> None:
        self._token = None
        self._owns_scope = False  # True if THIS call installed the scope

    def __enter__(self) -> "engine_cache_scope":
        # Re-entrancy guard: if a scope is already active, reuse it.
        if _ENGINE_CACHE.get() is not None:
            self._owns_scope = False
            return self
        # Install a new scope
        self._owns_scope = True
        self._token = _ENGINE_CACHE.set({})
        return self

    def __exit__(self, *exc) -> None:
        # Only reset if WE installed the scope (re-entrancy guard)
        if self._owns_scope and self._token is not None:
            _ENGINE_CACHE.reset(self._token)
            self._token = None
            self._owns_scope = False

    @property
    def stats(self) -> dict[str, int]:
        """Cache statistics (hits, misses, size). For telemetry/tests."""
        cache = _ENGINE_CACHE.get()
        if cache is None:
            return {"hits": 0, "misses": 0, "size": 0}
        # _hits and _misses are tracked on the cache dict itself
        return {
            "hits": cache.get("_hits", 0),
            "misses": cache.get("_misses", 0),
            "size": len(cache),
        }
