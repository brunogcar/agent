"""Auto-register file operations."""
import importlib
from pathlib import Path

# Auto-import all action modules
for py_file in Path(__file__).parent.glob("actions/*.py"):
    if py_file.name != "__init__.py":
        importlib.import_module(f"tools.file_ops.actions.{py_file.stem}")