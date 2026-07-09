"""swarm_ops — Multi-model swarm tool subpackage."""
from __future__ import annotations
import importlib
from pathlib import Path

from . import _registry  # noqa: F401

_actions_dir = Path(__file__).parent / "actions"
for py_file in sorted(_actions_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.swarm_ops.actions.{py_file.stem}"
        importlib.import_module(module_name)
