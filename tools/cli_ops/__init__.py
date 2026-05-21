"""Auto-register cli operations."""

import importlib
from pathlib import Path

# Import registry first
from ._registry import DISPATCH, register_action  # ← From parent, not actions

# Auto-import all action modules
for py_file in Path(__file__).parent.glob("actions/*.py"):
    if py_file.name not in ("__init__.py", "_registry.py"):
        importlib.import_module(f"tools.cli_ops.actions.{py_file.stem}")