"""Auto-registration initializer for agent operations.

This module ensures that all action handlers in tools/agent_core/actions/
and all role configs in tools/agent_core/roles/ are imported at startup,
which triggers their @register_action decorators and populates the
DISPATCH table in _registry.py and the ROLES dict.

How it works:
 1. Import _registry to ensure the DISPATCH dict exists
 2. Use pathlib to find all .py files in the actions/ subdirectory
 3. Dynamically import each action module using importlib
 4. Each imported module's @register_action decorators run automatically
 5. Use pathlib to find all .py files in the roles/ subdirectory
 6. Dynamically import each role module, validate exports, build ROLES dict
 7. Guard against duplicate role names

This pattern means:
 ✅ No manual list of actions or roles to maintain
 ✅ Adding a new action = just drop a file in actions/
 ✅ Adding a new role = just drop a file in roles/
 ✅ Removing an action or role = just delete the file
 ✅ Zero risk of forgetting to register an action or role

Note: The actions/ directory must contain only action handler modules
(one function per file, decorated with @register_action). Utility modules
should be placed elsewhere (e.g., agent_core/context.py).

Note: The roles/ directory must contain only role config modules
(each exporting SYSTEM_PROMPT and ROLE_CONFIG). Utility modules
should be placed elsewhere.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict

# Import _registry to ensure DISPATCH dict is initialized before we register actions
# noqa: F401 suppresses "imported but unused" warning — we import for side effects
from . import _registry  # noqa: F401

# ── Auto-discover actions ────────────────────────────────────────────────────
_actions_dir = Path(__file__).parent / "actions"
for py_file in sorted(_actions_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.agent_core.actions.{py_file.stem}"
        importlib.import_module(module_name)

# ── Auto-discover roles ──────────────────────────────────────────────────────
# Build a lookup dict: role_name -> {system_prompt, role_config}
ROLES: Dict[str, Dict[str, Any]] = {}

_roles_dir = Path(__file__).parent / "roles"
for py_file in sorted(_roles_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.agent_core.roles.{py_file.stem}"
        mod = importlib.import_module(module_name)

        # Validate required exports
        if not hasattr(mod, "SYSTEM_PROMPT"):
            raise ValueError(
                f"Role module '{module_name}' must export 'SYSTEM_PROMPT'. "
                f"Add: SYSTEM_PROMPT = '...'"
            )
        if not hasattr(mod, "ROLE_CONFIG"):
            raise ValueError(
                f"Role module '{module_name}' must export 'ROLE_CONFIG'. "
                f"Add: ROLE_CONFIG = {{'llm_role': '...', ...}}"
            )

        role_name = py_file.stem
        if role_name in ROLES:
            raise ValueError(
                f"Duplicate role registration: '{role_name}' already exists in ROLES. "
                f"Check for colliding role files in tools/agent_core/roles/."
            )

        ROLES[role_name] = {
            "system_prompt": mod.SYSTEM_PROMPT,
            "role_config": mod.ROLE_CONFIG,
        }
