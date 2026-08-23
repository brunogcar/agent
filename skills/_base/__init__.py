"""skills/_base/__init__.py — Shared infrastructure for all skills (CVM + B3 + BCB + investsite).

Provides the modular skill pattern's building blocks:
  - ModeSpec dataclass (mode metadata)
  - make_registry() factory (creates per-skill MODES dict + register_mode decorator)
  - build_manifest_modes() (turns registry into MANIFEST["modes"] dict)
  - list_modes() / get_mode() (registry accessors)
  - auto_discover_modes() (importlib-based modes/*.py auto-discovery)
  - make_route() (generates the route() dispatcher function)
  - engine_cached() decorator + engine_cache_scope (F7 cache)
  - ensure_fresh() + sync guard helpers (v1.14)

WHY THIS EXISTS:
  Before this module, each of the 11 skills (10 CVM + investsite) had its own
  _registry.py (~97 lines) + __init__.py (~88 lines) with near-identical code.
  That's ~1840 lines of duplication. Bug fixes (like the ModeSpec collision
  guard) had to be made in 11 places. This package centralizes the shared
  infrastructure so each skill's _registry.py shrinks to ~3 lines + __init__.py
  to ~20 lines.

PACKAGE STRUCTURE (split from the original skills/_base.py in Phase 3 Commit 2):
  skills/_base/
  ├── __init__.py        — this file: re-exports all public + private names
                           so `from skills._base import X` keeps working
                           (backward-compat for ~92 import sites repo-wide)
  ├── registry.py        — ModeSpec + make_registry + build_manifest_modes
                           + list_modes + get_mode + auto_discover_modes
  ├── route.py           — make_route + _route_with_sync_guard + _dispatch
                           + _SYNC_CHECKED (re-entrancy ContextVar)
  ├── html_gen.py        — _auto_generate_html (dashboard-mode HTML writer)
  ├── engine_cache.py    — _ENGINE_CACHE + engine_cached + engine_cache_scope
                           (3-layer cache: in-memory + DB + real fn)
  └── sync_guard.py      — SYNC_FRESHNESS_HOURS + _BRIDGE_SYNCED_TICKERS
                           + _bridge_lock + _HEAD_CACHE + _HEAD_TTL
                           + _source_last_sync + _parse_sync_ts
                           + _source_is_stale + _cvm_has_new_data
                           + _cvm_has_new_data_cached + _trigger_sync
                           + ensure_fresh

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

BACKWARD COMPATIBILITY:
  This package re-exports the same public + private names that the original
  skills/_base.py module exposed, so all 92 import sites (11 skill _registry.py
  + 11 __init__.py + 27 engine files + 6 engine_cache_scope consumers + tests)
  keep working without changes. Tests that monkeypatch via dotted string MUST
  use the new submodule path (e.g. "skills._base.sync_guard._source_is_stale")
  because monkeypatch.setattr patches the module __dict__ where the function
  is looked up at runtime, not where it's re-exported.
"""
from __future__ import annotations

# Registry: ModeSpec + factory + accessors + auto-discovery
from .registry import (
    ModeSpec,
    make_registry,
    build_manifest_modes,
    list_modes,
    get_mode,
    auto_discover_modes,
)

# Route: make_route + re-entrancy ContextVar (_SYNC_CHECKED is monkeypatched
# by test_chart_serialization.py via "skills._base.route._SYNC_CHECKED")
from .route import (
    make_route,
    _SYNC_CHECKED,
    _route_with_sync_guard,
    _dispatch,
)

# HTML generation for dashboard mode
from .html_gen import _auto_generate_html

# Engine cache: decorator + scope + ContextVar
from .engine_cache import (
    engine_cached,
    engine_cache_scope,
    _ENGINE_CACHE,
)

# Sync guard: ensure_fresh + helpers + constants
from .sync_guard import (
    ensure_fresh,
    _trigger_sync,
    _source_last_sync,
    _source_is_stale,
    _cvm_has_new_data,
    _cvm_has_new_data_cached,
    _parse_sync_ts,
    SYNC_FRESHNESS_HOURS,
    _BRIDGE_SYNCED_TICKERS,
    _bridge_lock,
    _HEAD_CACHE,
    _HEAD_TTL,
)


__all__ = [
    # Public API (imported by 92 files across the repo)
    "ModeSpec",
    "make_registry",
    "build_manifest_modes",
    "list_modes",
    "get_mode",
    "auto_discover_modes",
    "make_route",
    "engine_cached",
    "engine_cache_scope",
    # Public-looking constant
    "SYNC_FRESHNESS_HOURS",
    # Private but imported by name in tests (test_perf_infra + test_va_*)
    "ensure_fresh",
    "_ENGINE_CACHE",
    "_cvm_has_new_data",
    "_source_is_stale",
    # Private but referenced via monkeypatch dotted string in tests
    # (test_chart_serialization uses "skills._base.route._SYNC_CHECKED")
    "_SYNC_CHECKED",
    "_source_last_sync",
    "_trigger_sync",
    "_cvm_has_new_data_cached",
]
