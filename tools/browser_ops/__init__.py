"""browser_ops — Playwright browser automation subpackage."""
from __future__ import annotations

import importlib
from pathlib import Path

# Import _registry to ensure DISPATCH dict is initialized before action registration
from . import _registry  # noqa: F401

# ── Auto-discover actions ─────────────────────────────────────────────────
_actions_dir = Path(__file__).parent / "actions"
for py_file in sorted(_actions_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.browser_ops.actions.{py_file.stem}"
        importlib.import_module(module_name)

from tools.browser_ops.state import reset_state
from tools.browser_ops.loop import reset_loop

__all__ = ["reset_state", "reset_loop"]
