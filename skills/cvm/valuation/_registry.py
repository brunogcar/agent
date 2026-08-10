"""skills/cvm/valuation/_registry.py — Mode registry for valuation skill.

Delegates to skills._base for the shared ModeSpec + register_mode +
build_manifest_modes infrastructure. This file exists to give valuation
its own isolated MODES dict + to provide a stable import path for mode files:
    from skills.cvm.valuation._registry import register_mode
"""
from __future__ import annotations

from skills._base import make_registry

# Create valuation's own isolated MODES dict + register_mode decorator.
MODES, register_mode = make_registry()
