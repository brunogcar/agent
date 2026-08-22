"""skills/ddm/dividends/_registry.py - Mode registry for the dividends skill.

Delegates to skills._base for the shared ModeSpec + register_mode +
build_manifest_modes + auto_discover_modes + make_route infrastructure
when available (i.e. when merged into the agent tree). Falls back to a
minimal inline implementation for standalone testing.

This file gives dividends its own isolated MODES dict and a stable import
path for mode files:

    from skills.ddm.dividends._registry import register_mode

The fallback mirrors the real skills._base API surface (ModeSpec dataclass,
make_registry, build_manifest_modes, list_modes, get_mode, auto_discover_modes,
make_route). The sync guard (ensure_fresh) is intentionally omitted in the
fallback - tests set CVM_SKIP_SYNC=1 to bypass anyway.
"""

from __future__ import annotations

try:
    from skills._base import (
        make_registry, build_manifest_modes, list_modes, get_mode,
        auto_discover_modes, make_route,
    )
except ImportError:
    # Standalone fallback (no skills._base available).
    import importlib
    import inspect
    from dataclasses import dataclass, field
    from pathlib import Path
    from typing import Callable

    @dataclass
    class ModeSpec:
        """Mode metadata + the function that implements it."""
        name: str
        fn: Callable
        description: str = ""
        params: dict = field(default_factory=dict)
        include_in_all: bool = False
        examples: list = field(default_factory=list)
        params_set: set = field(default_factory=set)

    def make_registry() -> tuple:
        """Create a per-skill (MODES dict, register_mode decorator) pair."""
        MODES: dict = {}

        def register_mode(name, *, description="", params=None,
                          include_in_all=False, examples=None):
            def decorator(fn):
                if name in MODES:
                    raise ValueError(f"Duplicate mode registration: '{name}'")
                sig = inspect.signature(fn)
                accepted = set(sig.parameters.keys())
                MODES[name] = ModeSpec(
                    name=name, fn=fn, description=description,
                    params=params or {}, include_in_all=include_in_all,
                    examples=examples or [], params_set=accepted,
                )
                return fn
            return decorator
        return MODES, register_mode

    def build_manifest_modes(MODES):
        """Turn the registry into a MANIFEST["modes"] dict."""
        result = {}
        for name, spec in sorted(MODES.items()):
            result[name] = {
                "description": spec.description,
                "include_in_all": spec.include_in_all,
                "params": spec.params,
                "examples": spec.examples,
            }
        return result

    def list_modes(MODES):
        return sorted(MODES.keys())

    def get_mode(MODES, name):
        return MODES.get(name)

    def auto_discover_modes(package_path: str) -> None:
        """Import all modes/*.py files in a skill package."""
        pkg = importlib.import_module(package_path)
        modes_dir = Path(pkg.__file__).parent / "modes"
        if not modes_dir.is_dir():
            return
        for py_file in sorted(f for f in modes_dir.glob("*.py")
                              if f.name != "__init__.py"):
            importlib.import_module(f"{package_path}.modes.{py_file.stem}")

    def make_route(manifest_key, skill_name, MODES,
                   accept_sub_domain=False, required_sources=None):
        """Create a route() dispatcher (simplified - no sync guard)."""
        def _dispatch(mode, kwargs):
            if not mode:
                return {"status": "error",
                        "error": f"mode required. Options: {list(MODES.keys())}"}
            if mode not in MODES:
                return {"status": "error",
                        "error": f"Unknown mode '{mode}'. Available: {list(MODES.keys())}"}
            spec = MODES[mode]
            accepted = spec.params_set or set(
                inspect.signature(spec.fn).parameters.keys())
            filtered = {k: v for k, v in kwargs.items() if k in accepted}
            try:
                return spec.fn(**filtered)
            except Exception as e:
                return {"status": "error", manifest_key: skill_name,
                        "mode": mode, "error": str(e)}

        if accept_sub_domain:
            def route(sub_domain="", mode="", **kwargs):
                _ = sub_domain
                return _dispatch(mode, kwargs)
            return route
        else:
            def route(mode="", **kwargs):
                return _dispatch(mode, kwargs)
            return route


# Create dividends's own isolated MODES dict + register_mode decorator.
MODES, register_mode = make_registry()
