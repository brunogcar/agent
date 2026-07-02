"""Auto-register memory operations."""
import importlib
from pathlib import Path

from . import _registry  # noqa: F401
from ._registry import DISPATCH  # noqa: F401

for py_file in sorted(Path(__file__).parent.glob("actions/*.py")):
    if py_file.stem not in ("__init__", "_registry"):
        importlib.import_module(f"tools.memory_ops.actions.{py_file.stem}")

from tools.memory_ops.state import reset_state

__all__ = ["reset_state"]
