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
import os
import sys
import threading
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
    required_sources: list[str] | None = None,
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
        required_sources: [v1.14] List of data sources this skill needs (e.g.
                         ["dfp", "itr", "bridge"]). The route() wrapper checks
                         freshness before each dispatch and triggers force-sync
                         if any source is older than 24h (or missing). Set to
                         None or [] to disable. Tests use CVM_SKIP_SYNC=1.

    Returns:
        A route(mode="", **kwargs) function (or route(sub_domain="", mode="")
        if accept_sub_domain=True) that dispatches to the registered mode.

    Usage in __init__.py:
        # CVM skill with sync guard:
        route = make_route("sub_domain", "governance", MODES,
                           required_sources=["dfp", "itr", "bridge"])
        # CVM skill without sync guard:
        route = make_route("sub_domain", "governance", MODES)
        # Top-level flat domain:
        route = make_route("domain", "investsite", MODES, accept_sub_domain=True)
    """
    srcs = required_sources or []

    if accept_sub_domain:
        def route(sub_domain: str = "", mode: str = "", **kwargs) -> dict:
            # sub_domain is intentionally ignored (flat domain compat).
            _ = sub_domain
            return _route_with_sync_guard(srcs, manifest_key, skill_name, MODES, mode, kwargs)
        return route
    else:
        def route(mode: str = "", **kwargs) -> dict:
            return _route_with_sync_guard(srcs, manifest_key, skill_name, MODES, mode, kwargs)
        return route


def _auto_generate_html(skill_name: str, mode: str, kwargs: dict, result: dict) -> None:
    """Auto-generate an HTML dashboard file for dashboard mode results.

    [v5] Every time a skill's route(mode="dashboard", ...) produces a
    successful result with tabs, this function pipes the result into
    tools.report_ops.html.build_dashboard() and writes an HTML file.

    The HTML file is written to the REPORTS ROOT (workspace/reports/) with a
    company prefix: e.g. ``PETR4_valuation_dashboard.html``.

    The html_path is added to the result dict so callers can open it.

    Skipped when:
      - mode != "dashboard"
      - result status != "ok" or no tabs
      - CVM_SKIP_HTML=1 env var is set (for tests)

    NOTE: Re-entrancy is already handled by _SYNC_CHECKED — inner route()
    calls return early from _route_with_sync_guard before reaching here.

    Wrapped in try/except — NEVER breaks the dashboard result. On failure,
    prints a warning and continues without html_path.
    """
    # Only dashboard mode
    if mode != "dashboard":
        return
    # Only successful results with tabs
    if not isinstance(result, dict):
        return
    if result.get("status") != "ok":
        return
    if not result.get("tabs"):
        return
    # Escape hatch for tests
    if os.environ.get("CVM_SKIP_HTML") == "1":
        return

    try:
        from pathlib import Path as _Path
        import shutil as _shutil
        from tools.report_ops import html as _report_html

        # Get company/ticker for the filename prefix.
        # Try kwargs first (company / ticker / tickers list), then result dict.
        company = (kwargs.get("company") or kwargs.get("ticker") or "").strip()
        if not company:
            tickers = kwargs.get("tickers")
            if isinstance(tickers, list) and tickers:
                company = str(tickers[0]).strip()
        if not company and isinstance(result, dict):
            company = (result.get("company") or result.get("ticker") or "").strip()
            if isinstance(company, list) and company:
                company = str(company[0])
        safe_company = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in company
        ) if company else ""

        # Build the HTML via the report tool (writes to a temp subfolder).
        # build_dashboard creates 3 files: {title}.html, manifest.json, metrics.json
        _trace = f"auto_{skill_name}"
        _title = f"{skill_name} dashboard"
        html_result = _report_html.build_dashboard(
            trace_id=_trace,
            title=_title,
            data=result,
            config={},
        )
        src_path_str = html_result.get("html_path", "")
        if not src_path_str:
            return
        src_path = _Path(src_path_str)
        if not src_path.exists():
            return

        # Move ALL files (HTML + manifest.json + metrics.json) to REPORTS ROOT.
        # Reports root = workspace/reports/ (parent of the trace_id subfolder).
        reports_root = src_path.parent.parent
        prefix = f"{safe_company}_" if safe_company else ""
        sub_dir = src_path.parent  # workspace/reports/auto_{skill_name}/

        # Move the HTML file with company prefix.
        dst_html = reports_root / f"{prefix}{skill_name}_dashboard.html"
        if dst_html.exists():
            dst_html.unlink()
        _shutil.move(str(src_path), str(dst_html))

        # Move manifest.json + metrics.json to root with company prefix.
        for json_name in ("manifest.json", "metrics.json"):
            src_json = sub_dir / json_name
            if src_json.exists():
                json_prefix = f"{prefix}{skill_name}_dashboard_"
                dst_json = reports_root / f"{json_prefix}{json_name}"
                if dst_json.exists():
                    dst_json.unlink()
                _shutil.move(str(src_json), str(dst_json))

        # Remove the now-empty trace_id subfolder (and any empty parents).
        try:
            if sub_dir.exists() and not any(sub_dir.iterdir()):
                sub_dir.rmdir()
        except OSError:
            pass  # not empty or in use — leave it

        result["html_path"] = str(dst_html)
        print(f"  [html] {skill_name} dashboard → {dst_html}", flush=True)
    except Exception as e:
        # Never break the dashboard — just warn + record in result for visibility
        print(f"  [html] {skill_name} dashboard HTML generation failed: {e}", flush=True)
        if isinstance(result, dict):
            if "_html_errors" not in result:
                result["_html_errors"] = []
            result["_html_errors"].append(str(e))


def _route_with_sync_guard(
    srcs: list[str],
    manifest_key: str,
    skill_name: str,
    MODES: dict[str, ModeSpec],
    mode: str,
    kwargs: dict,
) -> dict:
    """Run sync guard + dispatch with re-entrancy protection.

    [v1.14] The re-entrancy guard wraps the ENTIRE route() call (sync check
    + dispatch), not just the sync check. This ensures that if a mode
    function (e.g., dashboard()) internally calls another route() (e.g.,
    annual()), the inner route() skips the sync check — it's already been
    done by the outer route().

    [v5] The outer route() call also auto-generates HTML for dashboard mode.
    Inner route() calls (re-entrancy) skip HTML generation because they
    return early from the _SYNC_CHECKED guard above.
    """
    # Re-entrancy guard: if we're already inside a route() call, skip sync.
    if _SYNC_CHECKED.get():
        # Inner call — just dispatch, no sync check, no HTML
        kwargs.pop("skip_sync", False)
        return _dispatch(manifest_key, skill_name, MODES, mode, kwargs)

    # Outer call — set guard, run sync check, dispatch, then reset guard
    token = _SYNC_CHECKED.set(True)
    try:
        skip_sync = kwargs.pop("skip_sync", False)
        sync_report = None
        if srcs:
            company = kwargs.get("company")
            sync_report = ensure_fresh(srcs, company=company, skip_sync=skip_sync)
        result = _dispatch(manifest_key, skill_name, MODES, mode, kwargs)
        if sync_report is not None:
            result["_sync"] = sync_report
        # [v5] Auto-generate HTML for dashboard mode (outer call only —
        # inner calls return early from the _SYNC_CHECKED guard above).
        _auto_generate_html(skill_name, mode, kwargs, result)
        return result
    finally:
        _SYNC_CHECKED.reset(token)


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


# ── Force Sync Guard (v1.14) ────────────────────────────────────────────────
#
# When a user calls a skill, check if the required data sources are stale
# (>24h since last sync). If stale, force-sync them BEFORE running the skill.
#
# This is NOT auto-sync (scheduled cron). It's on-demand when a skill is used.
# The first call of the day may take 30+ seconds (DFP sync); subsequent calls
# within 24h are fast.
#
# DESIGN (per LLM review consensus):
#   - 24h freshness window for ALL sources (earnings season releases daily)
#   - HEAD check before downloading (CVM only — compare Last-Modified header
#     to last sync timestamp). Timeout=5s. On network error → sync anyway
#     (safer to sync than to skip).
#   - Current-year-only force sync (not full history) for DFP/ITR/FRE/etc.
#   - bridge: sync only the requested ticker, not all tickers
#   - Failure path: proceed with stale data + warning (don't hard-fail)
#   - Escape hatches: CVM_SKIP_SYNC=1 env var + skip_sync=True kwarg
#   - Re-entrancy: ContextVar guard ensures ensure_fresh() runs at most
#     once per top-level route() call (dashboard composes other modes)

from datetime import datetime, timedelta

# Re-entrancy guard: ensures ensure_fresh() runs at most once per top-level
# route() call. Without this, dashboard() → annual() → quarterly() would
# each trigger ensure_fresh() separately.
_SYNC_CHECKED: ContextVar[bool] = ContextVar("_sync_checked", default=False)

# [Tier 0 #3] Session-level bridge sync dedup — tracks which tickers have been
# bridge-synced in this Python process. Prevents redundant bridge syncs when
# multiple skills run for the same ticker (valuation → financials → historical).
# [P1 #8] Protected by _bridge_lock to prevent TOCTOU race in concurrent execution.
_BRIDGE_SYNCED_TICKERS: set[str] = set()
_bridge_lock = threading.Lock()

# [P1 #6] HEAD check cache — 60min TTL. Prevents 104 redundant HTTP HEAD requests
# when running all 13 dashboards (13 skills × 8 CVM sources = 104 HEADs).
_HEAD_CACHE: dict[str, tuple[bool, float]] = {}  # key → (has_new_data, timestamp)
_HEAD_TTL = 3600  # 1 hour

# Freshness window (hours). A source is "stale" if its last sync is older
# than this, or if it has no sync_state entry at all.
SYNC_FRESHNESS_HOURS = 24


def _source_last_sync(source: str) -> str:
    """Get the last-sync timestamp for a data source (ISO string, or "").

    Delegates to skills.cvm._freshness.get_freshness() for CVM sources.
    """
    try:
        from skills.cvm._freshness import get_freshness
        fresh = get_freshness()
        return fresh.get(source, "")
    except Exception:
        return ""


def _parse_sync_ts(ts: str) -> datetime | None:
    """Parse a sync timestamp string to a LOCAL naive datetime.

    Handles mixed conventions in the codebase:
      - cotahist/brapi store UTC with tzinfo  (e.g. "2026-08-08T20:00:00+00:00")
      - bridge/dfp/itr store LOCAL naive     (e.g. "2026-08-08T17:00:00")

    If the timestamp has tzinfo (UTC), convert to local then strip tzinfo so
    it can be compared with datetime.now() (local naive) without producing
    negative ages.
    """
    try:
        last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if last.tzinfo is not None:
            # UTC timestamp → convert to local time, then strip tzinfo
            last = last.astimezone().replace(tzinfo=None)
        return last
    except (ValueError, TypeError):
        return None


def _source_is_stale(source: str, max_age_hours: int = SYNC_FRESHNESS_HOURS) -> bool:
    """Check if a data source is stale (last sync older than max_age_hours, or missing).

    A source is stale if:
      - Its last-sync timestamp is "" (never synced / DB missing), OR
      - Its last-sync timestamp is older than max_age_hours from now.
    """
    ts = _source_last_sync(source)
    if not ts:
        return True  # never synced
    last = _parse_sync_ts(ts)
    if last is None:
        return True  # can't parse → treat as stale
    age = datetime.now() - last
    return age > timedelta(hours=max_age_hours)


def _cvm_has_new_data(source: str, year: int) -> bool:
    """HEAD request to CVM URL — check if server has new data since last sync.

    Returns True if:
      - The remote Last-Modified header is newer than the last sync timestamp, OR
      - The HEAD request fails (network error, timeout) — safer to sync than skip.

    Returns False only if:
      - The HEAD succeeds AND Last-Modified is older than the last sync.

    Args:
        source: One of "dfp", "itr", "fca", "fre", "ipe", "vlmo", "cgvn", "cad".
        year: The year to check (e.g., 2025). Ignored for "cad" (no year in URL).
    """
    import requests
    import email.utils

    # [v4] All CVM sources now have URL maps — previously only dfp/itr/fca
    # were HEAD-checkable; fre/ipe/vlmo/cgvn/cad always returned True ("sync
    # anyway"), causing unnecessary re-downloads every route() call.
    url_map = {
        "dfp":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip",
        "itr":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip",
        "fca":  f"http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{year}.zip",
        "fre":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{year}.zip",
        "ipe":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip",
        "vlmo": f"http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_{year}.zip",
        "cgvn": f"http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/CGVN/DADOS/cgvn_cia_aberta_{year}.zip",
        # cad is a single CSV (no year) — always check the same URL.
        "cad":  f"https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
    }

    if source not in url_map:
        return True  # unknown source → sync anyway

    try:
        resp = requests.head(url_map[source], timeout=5, allow_redirects=True)
        remote_mtime_str = resp.headers.get("Last-Modified", "")
        if not remote_mtime_str:
            return True  # no Last-Modified header → sync
        remote_mtime = email.utils.parsedate_to_datetime(remote_mtime_str)
        # CVM's Last-Modified is UTC → convert to local naive for comparison
        if remote_mtime.tzinfo is not None:
            remote_mtime = remote_mtime.astimezone().replace(tzinfo=None)

        last_sync_str = _source_last_sync(source)
        if not last_sync_str:
            return True  # never synced → sync
        last_sync = _parse_sync_ts(last_sync_str)
        if last_sync is None:
            return True  # can't parse → sync

        return remote_mtime > last_sync
    except Exception:
        # Network error, timeout, parse error → safer to sync than skip
        return True


def _cvm_has_new_data_cached(source: str, year: int) -> bool:
    """HEAD check with 60min in-memory TTL.

    [P1 #6] Prevents 104 redundant HTTP HEAD requests when running all 13
    dashboards (13 skills × 8 CVM sources = 104 HEADs). The HEAD result
    only changes when CVM publishes new data (daily at most), so 1h TTL
    is more than enough.
    """
    import time as _time
    key = f"{source}:{year}"
    now = _time.time()

    if key in _HEAD_CACHE:
        result, ts = _HEAD_CACHE[key]
        if now - ts < _HEAD_TTL:
            return result

    result = _cvm_has_new_data(source, year)
    _HEAD_CACHE[key] = (result, now)
    return result


def _trigger_sync(source: str, company: str | None = None, trace_id: str = "") -> dict:
    """Trigger force-sync for a single data source. Returns sync result dict.

    Maps source names to their sync functions with the right args:
      - DFP/ITR/FRE/IPE: sync(years=[current_year], force=True)
      - FCA:             sync(year=current_year, force=True)
      - CAD:             sync(force=True)
      - VLMO/CGVN:       sync(year=current_year, force=True)
      - bridge:          sync(ticker=company, force=True) — only requested ticker
      - cotahist:        sync(year=current_year, force=True)
      - brapi:           sync_tickers(force=True)

    Args:
        source: One of the source names above.
        company: Ticker (for bridge sync). None for other sources.
        trace_id: Tracer ID for logging.
    """
    import traceback

    current_year = datetime.now().year
    # [v1.16 3T2025-fix] Also sync the PREVIOUS year for DFP/ITR/FRE/IPE.
    # CVM publishes quarterly ITR data throughout the year — 3T2025 (Q3) may
    # be published AFTER the initial 2025 sync ran. The old code only force-
    # synced current_year (2026), so late-published 2025 data was never
    # picked up. Now we sync both current + previous year for the 4 CVM
    # financial-statement sources (dfp/itr/fre/ipe).
    prev_year = current_year - 1

    # (module_path, fn_name, kwargs_fn) — kwargs_fn builds the kwargs dict
    # [v1.2] verbose=False for auto-syncs — ensure_fresh() runs during normal
    # skill use, so we don't want sync progress spam in stderr. Users who run
    # sync manually (python -c "from ... import sync; sync(...)") get verbose=True
    # by default.
    sync_map = {
        "dfp":          ("data_sources.cvm.dfp.sync_engine", "sync",
                         lambda: {"years": [current_year, prev_year], "force": True, "trace_id": trace_id, "verbose": False}),
        "itr":          ("data_sources.cvm.itr.sync_engine", "sync",
                         lambda: {"years": [current_year, prev_year], "force": True, "trace_id": trace_id, "verbose": False}),
        "fre":          ("data_sources.cvm.fre.sync_engine", "sync",
                         lambda: {"years": [current_year, prev_year], "force": True, "trace_id": trace_id, "verbose": False}),
        "ipe":          ("data_sources.cvm.ipe.sync_engine", "sync",
                         lambda: {"years": [current_year, prev_year], "force": True, "trace_id": trace_id, "verbose": False}),
        "fca":          ("data_sources.cvm.fca.sync_engine", "sync",
                         lambda: {"year": current_year, "force": True}),
        "cad":          ("data_sources.cvm.cad.sync_engine", "sync",
                         lambda: {"force": True, "trace_id": trace_id, "verbose": False}),
        "vlmo":         ("data_sources.cvm.vlmo.sync_engine", "sync",
                         lambda: {"year": current_year, "force": True}),
        "cgvn":         ("data_sources.cvm.cgvn.sync_engine", "sync",
                         lambda: {"year": current_year, "force": True}),
        "bridge":       ("data_sources.cvm.bridge.sync_engine", "sync",
                         lambda: {"ticker": company or "", "force": False, "trace_id": trace_id}),
        "cotahist":     ("data_sources.b3.cotahist.sync_engine", "sync",
                         lambda: {"year": current_year, "force": True, "trace_id": trace_id}),
        "b3_dividends": ("data_sources.b3.dividends.sync_engine", "sync",
                         lambda: {"force": True, "trace_id": trace_id}),
        "brapi":        ("data_sources.b3.brapi.sync_engine", "sync_tickers",
                         lambda: {"force": True}),
        # [new commit] BCB SGS sync — REQUIRED_SOURCES in historical includes "sgs"
        # but sync_map had no entry, so every dashboard run failed the sgs sync
        # silently with "unknown source 'sgs'". This meant Selic/CDI/IPCA data
        # could go stale indefinitely. sync_all(force=False) re-fetches only
        # stale series (uses internal TTL).
        "sgs":          ("data_sources.bcb.sgs.sync_engine", "sync_all",
                         lambda: {"force": True}),
    }

    if source not in sync_map:
        return {"status": "error", "source": source,
                "error": f"unknown source '{source}' (no sync function mapped)"}

    module_path, fn_name, kwargs_fn = sync_map[source]
    try:
        mod = importlib.import_module(module_path)
        sync_fn = getattr(mod, fn_name)
        kwargs = kwargs_fn()
        print(f"  [sync] Force-syncing {source} (kwargs: {kwargs})...", flush=True)
        result = sync_fn(**kwargs)
        print(f"  [sync] {source} done.", flush=True)
        return {"status": "ok", "source": source, "result": result}
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  [sync] {source} FAILED: {e}", flush=True)
        return {"status": "error", "source": source,
                "error": str(e), "traceback": tb}


def ensure_fresh(
    sources: list[str],
    company: str | None = None,
    skip_sync: bool = False,
    trace_id: str = "",
) -> dict:
    """Ensure all named data sources are fresh (synced within 24h).

    For each source:
      1. Check freshness via _source_is_stale() (24h window).
      2. If stale AND not skip_sync:
         a. For CVM sources (dfp/itr/fca): HEAD check — only sync if CVM
            has new data (or HEAD fails).
         b. For other sources: sync directly.
      3. On sync failure: record error but DON'T raise (proceed with stale).
      4. Record result.

    Args:
        sources: List of source names (e.g., ["dfp", "itr", "bridge"]).
        company: Ticker (for bridge sync — only syncs this ticker).
        skip_sync: If True, only check — don't trigger sync.
        trace_id: Tracer ID for sync logging.

    Returns:
        {"synced": [...], "fresh": [...], "errors": [...], "skipped": [...]}

    Escape hatches (sync is NEVER triggered):
      - CVM_SKIP_SYNC=1 env var
      - skip_sync=True kwarg
    """
    # Global escape hatch for tests
    if os.environ.get("CVM_SKIP_SYNC") == "1":
        skip_sync = True

    synced: list[str] = []
    fresh: list[str] = []
    errors: list[dict] = []
    skipped: list[str] = []

    # [v2.1] CVM sources ALWAYS get a HEAD check against the server — not
    # just when the local DB is >24h old. This catches new quarterly filings
    # published within the 24h window. Non-CVM sources (cotahist, brapi,
    # bridge, sgs, index) keep the 24h freshness window.
    _CVM_SOURCES = {"dfp", "itr", "fca", "fre", "ipe", "cad", "vlmo", "cgvn"}

    # [Tier 0 #2] Parallelize CVM HEAD checks — was 8 sequential HTTP requests
    # (3-40s), now concurrent (~5s max). The sync itself stays sequential
    # (same DB files), but the HEAD check is the slow part.
    cvm_sources_in_list = [s for s in sources if s in _CVM_SOURCES]
    cvm_head_results: dict[str, bool] = {}  # source → has_new_data

    if cvm_sources_in_list and not skip_sync:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        current_year = datetime.now().year
        print(f"  [sync] Checking CVM HEAD for {len(cvm_sources_in_list)} sources (parallel)...", flush=True)

        def _do_head_check(src):
            return src, _cvm_has_new_data_cached(src, current_year)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_do_head_check, s): s for s in cvm_sources_in_list}
            for future in as_completed(futures):
                src, has_new = future.result()
                cvm_head_results[src] = has_new

    for source in sources:
        # CVM sources: use the parallel HEAD-check results
        if source in _CVM_SOURCES:
            if skip_sync:
                skipped.append(source)
                continue
            has_new = cvm_head_results.get(source, True)  # default True if missing
            if not has_new:
                print(f"  [sync] {source} HEAD: up to date (no sync needed)", flush=True)
                fresh.append(source)
                continue
            # CVM has new data → trigger sync
            print(f"  [sync] {source} HEAD: new data available → force-sync", flush=True)
            sync_result = _trigger_sync(source, company=company, trace_id=trace_id)
            sync_status = sync_result.get("status")
            if sync_status in ("ok", "skipped"):
                synced.append(source)
            else:
                errors.append({
                    "source": source,
                    "error": sync_result.get("error", "unknown sync error"),
                })
            continue

        # Non-CVM sources: use 24h freshness window
        # [Tier 0 #3] Bridge dedup: skip bridge sync if this ticker was already
        # synced in this Python session (valuation → financials → historical all
        # sync bridge for the same PETR4 — only the first should actually sync).
        # [P1 #8] Protected by _bridge_lock to prevent TOCTOU race.
        if source == "bridge" and company:
            with _bridge_lock:
                if company.upper() in _BRIDGE_SYNCED_TICKERS:
                    print(f"  [sync] bridge: fresh (synced earlier this session for {company})", flush=True)
                    fresh.append(source)
                    continue

        if not _source_is_stale(source):
            _ts = _source_last_sync(source)
            _age = ""
            if _ts:
                _last = _parse_sync_ts(_ts)
                if _last is not None:
                    _age_h = int((datetime.now() - _last).total_seconds() / 3600)
                    _age = f" ({_age_h}h ago)"
            print(f"  [sync] {source}: fresh{_age}", flush=True)
            fresh.append(source)
            continue

        if skip_sync:
            skipped.append(source)
            continue

        print(f"  [sync] {source}: stale (>24h) → force-sync", flush=True)
        # Trigger force-sync (blocking)
        sync_result = _trigger_sync(source, company=company, trace_id=trace_id)
        sync_status = sync_result.get("status")
        # Treat both "ok" (synced) and "skipped" (already up-to-date) as success
        if sync_status in ("ok", "skipped"):
            synced.append(source)
            # [Tier 0 #3] Record bridge sync for session dedup
            # [P1 #8] Protected by _bridge_lock
            if source == "bridge" and company:
                with _bridge_lock:
                    _BRIDGE_SYNCED_TICKERS.add(company.upper())
        else:
            errors.append({
                "source": source,
                "error": sync_result.get("error", "unknown sync error"),
            })

    return {
        "synced": synced,
        "fresh": fresh,
        "errors": errors,
        "skipped": skipped,
    }
