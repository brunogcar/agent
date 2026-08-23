"""skills/_base/registry.py — Mode registry factory + accessors + auto-discovery.

Provides:
  - ModeSpec dataclass (mode metadata)
  - make_registry() factory (creates per-skill MODES dict + register_mode decorator)
  - build_manifest_modes() (turns registry into MANIFEST["modes"] dict)
  - list_modes() / get_mode() (registry accessors)
  - auto_discover_modes() (importlib-based modes/*.py auto-discovery)

Part of the skills/_base/ package split (was originally in skills/_base.py).
"""
from __future__ import annotations

import importlib
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


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
