"""skills/cvm/governance/_registry.py — Mode registry for governance skill.

Delegates to skills._base for the shared ModeSpec + register_mode + 
build_manifest_modes infrastructure. This file exists to give governance
its own isolated MODES dict + to provide a stable import path for mode files:
    from skills.cvm.governance._registry import register_mode

Adding a new mode = drop a file in modes/ + @register_mode(). No edits to
this file or __init__.py needed.
"""
from __future__ import annotations

from skills._base import make_registry, build_manifest_modes, list_modes, get_mode

# Create governance's own isolated MODES dict + register_mode decorator.
MODES, register_mode = make_registry()
