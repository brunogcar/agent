"""CLI operations package.

Auto-imports all action modules to ensure @register_action decorators
populate DISPATCH before cli.py facade is imported.

Import order is critical: action modules must be loaded before
`tools.cli.py` accesses DISPATCH for @meta_tool docstring generation.
Without these imports, DISPATCH would be empty and @meta_tool would
raise ValueError at import time.

The original auto-discovery via importlib + Path.glob is preserved.
Do NOT replace with hardcoded imports — that breaks auto-discovery
when new action modules are added.
"""
from __future__ import annotations

import importlib
from pathlib import Path

# Import registry first (needed by action modules)
from ._registry import DISPATCH, register_action  # noqa: F401

# Auto-import all action modules — triggers @register_action decorators
for py_file in Path(__file__).parent.glob("actions/*.py"):
    if py_file.name not in ("__init__.py", "_registry.py"):
        importlib.import_module(f"tools.cli_ops.actions.{py_file.stem}")
