"""Auto-registration initializer for report operations.

This module ensures that all action handlers in tools/report_ops/actions/
are imported at startup, which triggers their @register_action decorators
and populates the DISPATCH table in _registry.py.

How it works:
 1. Import _registry to ensure the DISPATCH dict exists
 2. Use pathlib to find all .py files in the actions/ subdirectory
 3. Dynamically import each module using importlib
 4. Each imported module's @register_action decorators run automatically

This pattern means:
 ✅ No manual list of actions to maintain
 ✅ Adding a new action = just drop a file in actions/
 ✅ Removing an action = just delete the file
 ✅ Zero risk of forgetting to register an action

Note: The actions/ directory must contain only action handler modules
(one function per file, decorated with @register_action). Utility modules
should be placed elsewhere (e.g., report_ops/helpers.py).
"""
import importlib
from pathlib import Path

# Import _registry to ensure DISPATCH dict is initialized before we register actions
# noqa: F401 suppresses "imported but unused" warning — we import for side effects
from . import _registry  # noqa: F401

# Auto-discover and import all action handler modules from the actions/ subdirectory
# This triggers @register_action decorators, populating DISPATCH automatically
for py_file in Path(__file__).parent.glob("actions/*.py"):
    # Skip __init__.py — it's not an action handler
    if py_file.name != "__init__.py":
        # Construct the full module path: tools.report_ops.actions.<stem>
        module_name = f"tools.report_ops.actions.{py_file.stem}"
        # Import the module — this executes its top-level code, including decorators
        importlib.import_module(module_name)
