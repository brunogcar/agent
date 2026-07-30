"""skills/cvm/shareholders/_registry.py — Mode registry for shareholders skill.

Delegates to skills._base for the shared ModeSpec + register_mode +
build_manifest_modes infrastructure. This file exists to give shareholders
its own isolated MODES dict + to provide a stable import path for mode files:
    from skills.cvm.shareholders._registry import register_mode
"""
from __future__ import annotations

from skills._base import make_registry, build_manifest_modes, list_modes, get_mode

# Create shareholders's own isolated MODES dict + register_mode decorator.
MODES, register_mode = make_registry()
