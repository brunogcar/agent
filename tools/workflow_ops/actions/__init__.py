"""tools/workflow_ops/actions/__init__.py — Action handler auto-discovery.

Each module here imports `register_action` from tools.workflow_ops._registry
and decorates its top-level handler. This __init__.py globs the directory
and imports all .py files (except __init__.py itself), triggering
registration.

Adding a new action: drop a new file here, define a handler decorated with
@register_action("workflow", "<action_name>", ...). The facade will pick it
up automatically on next import — no edits to this file needed.
"""
from __future__ import annotations
import importlib
from pathlib import Path

_actions_dir = Path(__file__).parent
for py_file in sorted(_actions_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.workflow_ops.actions.{py_file.stem}"
        importlib.import_module(module_name)
