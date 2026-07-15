"""schedule_ops — Scheduling tool subpackage.

Auto-discovers all action handlers under actions/ at import time so the
DISPATCH dict in _registry.py is populated before the schedule facade reads
it for @meta_tool Literal generation.

[DESIGN] WHY AUTO-DISCOVERY: every action module must be imported so its
@register_action decorator runs. Globbing the actions/ directory keeps the
registration list authoritative — adding a new action file is the only
change needed (no facade edits, no manual import list to maintain).

Mirrors notify_ops/__init__.py exactly.
"""
from __future__ import annotations
import importlib
from pathlib import Path

from . import _registry  # noqa: F401 — ensures DISPATCH exists before actions populate it

_actions_dir = Path(__file__).parent / "actions"
for py_file in sorted(_actions_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.schedule_ops.actions.{py_file.stem}"
        importlib.import_module(module_name)
