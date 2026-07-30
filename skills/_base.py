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

import importlib
import inspect
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
    """
    name: str
    fn: Callable
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)
    include_in_all: bool = False
    examples: list[str] = field(default_factory=list)


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
            MODES[name] = ModeSpec(
                name=name,
                fn=fn,
                description=description,
                params=params or {},
                include_in_all=include_in_all,
                examples=examples or [],
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

    Args:
        package_path: Dotted package path, e.g. "skills.cvm.governance"
                      or "skills.investsite". Use __name__ in __init__.py.
    """
    pkg = importlib.import_module(package_path)
    modes_dir = Path(pkg.__file__).parent / "modes"
    for py_file in sorted(modes_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
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
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", manifest_key: skill_name,
                "mode": mode, "error": str(e)}
