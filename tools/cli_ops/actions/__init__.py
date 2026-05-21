"""
Auto-discover and register all action handlers for cli meta-tool.

Similar to file_ops/__init__.py, this automatically imports all .py files
in the actions/ directory (except __init__.py and _registry.py) to trigger
auto-registration via @register_action decorators.

New actions can be added simply by creating a new .py file in this directory
with @register_action decorated functions - no need to edit this file.
"""

import importlib
from pathlib import Path

# Import the registry (defines DISPATCH dict and register_action decorator)
from tools.cli_ops.actions._registry import DISPATCH

# Auto-import all action modules in this directory
# This triggers @register_action decorators to populate DISPATCH
for py_file in Path(__file__).parent.glob("*.py"):
    if py_file.name not in ("__init__.py", "_registry.py"):
        module_name = f"tools.cli_ops.actions.{py_file.stem}"
        importlib.import_module(module_name)