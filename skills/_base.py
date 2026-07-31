"""skills/_base.py — Shared infrastructure for all skills (CVM + investsite).

Provides the modular skill pattern's building blocks:
  - ModeSpec dataclass (mode metadata)
  - make_registry() factory (creates per-skill MODES dict + register_mode decorator)
  - build_manifest_modes() (turns registry into MANIFEST["modes"] dict)
  - list_modes() / get_mode() (registry accessors)
  - auto_discover_modes() (importlib-based modes/*.py auto-discovery)
  - make_route() (generates the route() dispatcher function)

WHY THIS EXISTS:
  Before this module, each of the 11 skills (10 CVM + investsite) had its own
  _registry.py (~97 lines) + __init__.py (~88 lines) with near-identical code.
  That's ~1840 lines of duplication. Bug fixes (like the ModeSpec collision
  guard) had to be made in 11 places. This module centralizes the shared
  infrastructure so each skill's _registry.py shrinks to ~3 lines + __init__.py
  to ~20 lines.

HOW TO USE (when creating a new skill):

1. Create skills/<domain>/<skill>/_registry.py:
     from skills._base import make_registry
     MODES, register_mode = make_registry()

2. Create skills/<domain>/<skill>/modes/<mode>.py:
     from skills.<domain>.<skill>._registry import register_mode

     @register_mode("my_mode", description="...", params={...})
     def my_mode(company="") -> dict:
         ...

3. Create skills/<domain>/<skill>/__init__.py:
     from skills._base import auto_discover_modes, make_route, build_manifest_modes
     from skills.<domain>.<skill>._registry import MODES

     auto_discover_modes(__name__)
     MANIFEST = {
         "sub_domain": "<skill>",
         "description": "...",
         "source": "...",
         "storage": "...",
         "modes": build_manifest_modes(MODES),
     }
     route = make_route("sub_domain", "<skill>", MODES)

   For a top-level flat domain (like investsite), use:
     route = make_route("domain", "investsite", MODES, accept_sub_domain=True)
     MANIFEST = {"domain": "investsite", "has_sub_domains": False, ...}

DESIGN DECISIONS:
  - Each skill gets its OWN MODES dict via make_registry(). This prevents
    cross-skill mode name pollution (e.g., "dashboard" exists in all 11 skills
    but each is a different function).
  - register_mode is a closure over MODES, so the @register_mode decorator
    API stays the same: @register_mode("name", description=..., params=...).
  - auto_discover_modes(__name__) uses the package's __name__ to find its
    modes/ subdirectory — works for both skills.cvm.governance and
    skills.investsite.
  - make_route generates a route() with the right signature (CVM skills
    don't accept sub_domain; investsite does for dispatcher compat).
"""
from __future__ import annotations

import functools
import importlib
import inspect
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ── ModeSpec dataclass ───────────────────────────────────────────────────────

@dataclass
class ModeSpec:
    """Specification for a skill mode.

    Attributes:
        name:        Mode name (file name without .py). "practices", "score", etc.
        fn:          Callable that implements the mode. fn(**kwargs) -> dict.
        description: Human-readable description for manifest + help.
        params:      Dict of param_name -> description string.
        include_in_all: If True, this mode runs when sub_domain="all".
        examples:    List of example call strings.
        params_set:  [v1.1] Cached set of accepted parameter names (from
                     inspect.signature(fn)). Avoids re-calling inspect.signature
                     on every route() dispatch.
    """
    name: str
    fn: Callable
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)
    include_in_all: bool = False
    examples: list[str] = field(default_factory=list)
    params_set: set = field(default_factory=set)


# ── Registry factory ─────────────────────────────────────────────────────────

def make_registry() -> tuple[dict[str, ModeSpec], Callable]:
    """Create a per-skill (MODES dict, register_mode decorator) pair.

    Each skill must call this once in its _registry.py to get its own isolated
    MODES dict. This prevents cross-skill mode name pollution.

    Returns:
        (MODES, register_mode) — MODES is an empty dict that will be populated
        by @register_mode; register_mode is the decorator for mode files.

    Usage in _registry.py:
        from skills._base import make_registry
        MODES, register_mode = make_registry()

    Usage in modes/my_mode.py:
        from skills.cvm.governance._registry import register_mode

        @register_mode("my_mode", description="...", params={...})
        def my_mode(company="") -> dict:
            ...
    """
    MODES: dict[str, ModeSpec] = {}

    def register_mode(
        name: str,
        *,
        description: str = "",
        params: dict[str, str] | None = None,
        include_in_all: bool = False,
        examples: list[str] | None = None,
    ) -> Callable:
        """Decorator to register a mode in this skill's MODES dict.

        Args:
            name:           Mode name (must be unique within this skill).
            description:    Human-readable description for MANIFEST + help.
            params:         Dict of param_name -> description string.
            include_in_all: If True, this mode runs when sub_domain="all".
            examples:       List of example call strings.

        Raises:
            ValueError: If a mode with this name is already registered.
        """
        def decorator(fn: Callable) -> Callable:
            if name in MODES:
                raise ValueError(f"Duplicate mode registration: '{name}'")
            # [v1.1] Cache the function's accepted parameter names once at
            # registration time, so route() doesn't re-call inspect.signature
            # on every dispatch.
            sig = inspect.signature(fn)
            accepted = set(sig.parameters.keys())
            MODES[name] = ModeSpec(
                name=name,
                fn=fn,
                description=description,
                params=params or {},
                include_in_all=include_in_all,
                examples=examples or [],
                params_set=accepted,
            )
            return fn
        return decorator

    return MODES, register_mode


# ── Registry accessors ───────────────────────────────────────────────────────

def build_manifest_modes(MODES: dict[str, ModeSpec]) -> dict:
    """Build the MANIFEST['modes'] dict from registered ModeSpecs.

    Args:
        MODES: The skill's MODES dict (from make_registry()).

    Returns:
        Dict of mode_name -> {description, include_in_all, params, examples}.
    """
    result = {}
    for name, spec in sorted(MODES.items()):
        result[name] = {
            "description": spec.description,
            "include_in_all": spec.include_in_all,
            "params": spec.params,
            "examples": spec.examples,
        }
    return result


def list_modes(MODES: dict[str, ModeSpec]) -> list[str]:
    """Return sorted list of registered mode names."""
    return sorted(MODES.keys())


def get_mode(MODES: dict[str, ModeSpec], name: str) -> ModeSpec | None:
    """Get a ModeSpec by name, or None if not registered."""
    return MODES.get(name)


# ── Auto-discovery ───────────────────────────────────────────────────────────

def auto_discover_modes(package_path: str) -> None:
    """Auto-discover and import all modes/*.py files in a skill package.

    Each mode module's @register_mode decorator populates the skill's MODES
    dict at import time. This function must be called from the skill's
    __init__.py AFTER importing the _registry (so MODES exists) and BEFORE
    building the MANIFEST (so all modes are registered).

    [v1.1] Added warning when modes/ directory is missing or empty —
    prevents a silent 0-mode skill (e.g. typo'd folder name) from going
    unnoticed until a user tries to call it.

    Args:
        package_path: Dotted package path, e.g. "skills.cvm.governance"
                      or "skills.investsite". Use __name__ in __init__.py.
    """
    pkg = importlib.import_module(package_path)
    modes_dir = Path(pkg.__file__).parent / "modes"

    if not modes_dir.is_dir():
        print(f"[skills._base] WARNING: no modes/ directory found for "
              f"{package_path} — skill will have 0 modes. Check the folder "
              f"name for typos.", file=sys.stderr)
        return

    py_files = sorted(f for f in modes_dir.glob("*.py") if f.name != "__init__.py")
    if not py_files:
        print(f"[skills._base] WARNING: modes/ directory for {package_path} "
              f"is empty (no .py files except __init__.py) — skill will have "
              f"0 modes.", file=sys.stderr)
        return

    for py_file in py_files:
        module_name = f"{package_path}.modes.{py_file.stem}"
        importlib.import_module(module_name)


# ── Route factory ────────────────────────────────────────────────────────────

def make_route(
    manifest_key: str,
    skill_name: str,
    MODES: dict[str, ModeSpec],
    accept_sub_domain: bool = False,
) -> Callable:
    """Create a route() dispatcher function for a skill.

    Args:
        manifest_key:    "sub_domain" for CVM skills, "domain" for top-level
                         flat domains like investsite. Used in error responses.
        skill_name:      Skill name (e.g. "governance", "investsite"). Used in
                         error responses.
        MODES:           The skill's MODES dict (from make_registry()).
        accept_sub_domain: If True, route() accepts a sub_domain param (ignored)
                         for dispatcher compatibility. investsite needs this;
                         CVM skills don't (their dispatcher resolves sub_domain
                         before calling route()).

    Returns:
        A route(mode="", **kwargs) function (or route(sub_domain="", mode="")
        if accept_sub_domain=True) that dispatches to the registered mode.

    Usage in __init__.py:
        # CVM skill:
        route = make_route("sub_domain", "governance", MODES)
        # Top-level flat domain:
        route = make_route("domain", "investsite", MODES, accept_sub_domain=True)
    """
    if accept_sub_domain:
        def route(sub_domain: str = "", mode: str = "", **kwargs) -> dict:
            # sub_domain is intentionally ignored (flat domain compat).
            _ = sub_domain
            return _dispatch(manifest_key, skill_name, MODES, mode, kwargs)
        return route
    else:
        def route(mode: str = "", **kwargs) -> dict:
            return _dispatch(manifest_key, skill_name, MODES, mode, kwargs)
        return route


def _dispatch(
    manifest_key: str,
    skill_name: str,
    MODES: dict[str, ModeSpec],
    mode: str,
    kwargs: dict,
) -> dict:
    """Internal: dispatch a mode call (shared by both route() variants)."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MODES.keys())}"}
    if mode not in MODES:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MODES.keys())}"}

    spec = MODES[mode]
    fn = spec.fn
    # [v1.1] Use cached params_set instead of re-calling inspect.signature
    # on every dispatch (Qwen's performance finding).
    accepted = spec.params_set
    if not accepted:
        # Fallback: compute on first use if cache wasn't populated
        accepted = set(inspect.signature(fn).parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", manifest_key: skill_name,
                "mode": mode, "error": str(e)}


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

    Cache keys:
      - at_fn:      (fn.__name__, company, str(date))
      - periods_fn: (fn.__name__, company, "__periods__")

    None values ARE cached (prevents re-querying missing data).

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
        if cache is None:
            # No scope active → passthrough (zero overhead)
            return fn(*args, **kwargs)
        # Build cache key from function name + positional args.
        # at_fn(company, date) → (fn_name, company, date)
        # periods_fn(company) → (fn_name, company) — no date arg
        key = (fn.__name__,) + tuple(str(a) for a in args)
        if key in cache:
            cache["_hits"] = cache.get("_hits", 0) + 1
            return cache[key]
        cache["_misses"] = cache.get("_misses", 0) + 1
        cache[key] = fn(*args, **kwargs)
        return cache[key]
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
