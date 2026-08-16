"""skills/b3/options/_registry.py — Mode registry for the options skill.

Delegates to skills._base.make_registry() for the shared ModeSpec +
register_mode + build_manifest_modes + auto_discover_modes + make_route
infrastructure. This file gives options its own isolated MODES dict and a
stable import path for mode files:

    from skills.b3.options._registry import register_mode
"""
from __future__ import annotations

from skills._base import make_registry

MODES, register_mode = make_registry()
