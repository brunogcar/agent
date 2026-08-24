"""skills/ddm/juros/_registry.py — Mode registry for the juros skill.

Delegates to skills._base for the shared ModeSpec + make_registry +
build_manifest_modes + auto_discover_modes + make_route infrastructure.
This file exists to give juros its own isolated MODES dict + to provide
a stable import path for mode files:

    from skills.ddm.juros._registry import register_mode

Adding a new mode = drop a file in modes/ + @register_mode(). No edits to
this file or __init__.py needed.
"""
from __future__ import annotations

from skills._base import (
    make_registry, build_manifest_modes, list_modes, get_mode,
    auto_discover_modes, make_route,
)

# Create juros's own isolated MODES dict + register_mode decorator.
MODES, register_mode = make_registry()
