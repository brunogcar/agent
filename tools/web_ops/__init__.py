"""web_ops — Web search and scraping subpackage.

Auto-discovers action modules in actions/ at import time.
Import this module (or any submodule that triggers it) before
instantiating the web() facade so that DISPATCH is fully populated.
"""
from __future__ import annotations

import importlib
from pathlib import Path

# Import _registry to ensure DISPATCH dict is initialized before action registration
from . import _registry  # noqa: F401

# ── Auto-discover actions ─────────────────────────────────────────────────
# sorted() ensures deterministic import order across filesystems.
_actions_dir = Path(__file__).parent / "actions"
for py_file in sorted(_actions_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.web_ops.actions.{py_file.stem}"
        importlib.import_module(module_name)

from tools.web_ops.state import reset_state, reset_loop

__all__ = ["reset_state", "reset_loop"]
