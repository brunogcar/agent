"""skills/investsite/_registry.py — Mode registry + auto-discovery.

Central dispatch table for investsite modes. Each mode lives in its own file
under modes/ and registers itself via @register_mode.

This mirrors the tools/ pattern (tools/git_ops/_registry.py + actions/)
but adapted for skills: modes/ instead of actions/, MODES instead of DISPATCH.

Auto-discovery:
  1. __init__.py imports this module (ensures MODES dict exists)
  2. __init__.py auto-discovers modes/*.py via importlib
  3. Each mode module's @register_mode decorator populates MODES

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py.

Note: investsite is a flat top-level domain (not under cvm/), so the
MANIFEST uses "domain" instead of "sub_domain". This registry is identical
in structure to the CVM skill registries (governance/_registry.py +
screener/_registry.py + shareholders/_registry.py + insider/_registry.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ModeSpec:
    """Specification for an investsite mode.

    Attributes:
        name:        Mode name (file name without .py). "indicators", "statements", etc.
        fn:          Callable that implements the mode. fn(**kwargs) -> dict.
        description: Human-readable description for manifest + help.
        params:      Dict of param_name -> description string.
        include_in_all: If True, this mode runs when mode="all" (kept for
                       symmetry with CVM skills — investsite currently has no
                       "all" dispatch, but the flag is preserved).
        examples:    List of example call strings.
    """
    name: str
    fn: Callable
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)
    include_in_all: bool = False
    examples: list[str] = field(default_factory=list)


# Global registry: mode_name -> ModeSpec
MODES: dict[str, ModeSpec] = {}


def register_mode(
    name: str,
    *,
    description: str = "",
    params: dict[str, str] | None = None,
    include_in_all: bool = False,
    examples: list[str] | None = None,
) -> Callable:
    """Decorator to register an investsite mode.

    Usage in modes/indicators.py:
        @register_mode("indicators", description="...", params={...})
        def indicators(ticker="") -> dict:
            ...
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


def list_modes() -> list[str]:
    """Return sorted list of registered mode names."""
    return sorted(MODES.keys())


def get_mode(name: str) -> ModeSpec | None:
    """Get a ModeSpec by name, or None if not registered."""
    return MODES.get(name)


def build_manifest_modes() -> dict:
    """Build the MANIFEST['modes'] dict from registered ModeSpecs."""
    result = {}
    for name, spec in sorted(MODES.items()):
        result[name] = {
            "description": spec.description,
            "include_in_all": spec.include_in_all,
            "params": spec.params,
            "examples": spec.examples,
        }
    return result
