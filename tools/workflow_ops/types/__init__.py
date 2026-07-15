"""tools/workflow_ops/types/__init__.py — Type handler auto-discovery.

Each module here imports `register_type` from tools.workflow_ops._type_registry
and decorates its top-level handler. This __init__.py globs the directory
and imports all .py files (except __init__.py itself), triggering
registration into TYPE_DISPATCH.

Adding a new type: drop a new file here, define a handler decorated with
@register_type("<type_name>", help_text="..."). The `run` action handler
will pick it up automatically via TYPE_DISPATCH on next import — no edits
to this file needed.
"""
from __future__ import annotations
import importlib
from pathlib import Path

_types_dir = Path(__file__).parent
for py_file in sorted(_types_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.workflow_ops.types.{py_file.stem}"
        importlib.import_module(module_name)
