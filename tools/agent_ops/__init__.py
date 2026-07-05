"""Auto-registration initializer for agent operations.

This module ensures that all action handlers in tools/agent_ops/actions/
and all role configs in tools/agent_ops/roles/ are imported at startup,
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
should be placed elsewhere (e.g., agent_ops/context.py).

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
        module_name = f"tools.agent_ops.actions.{py_file.stem}"
        importlib.import_module(module_name)

# ── Auto-discover roles ──────────────────────────────────────────────────────
# Build a lookup dict: role_name -> {system_prompt, role_config}
ROLES: Dict[str, Dict[str, Any]] = {}

_roles_dir = Path(__file__).parent / "roles"
for py_file in sorted(_roles_dir.glob("*.py")):
    if py_file.name != "__init__.py":
        module_name = f"tools.agent_ops.roles.{py_file.stem}"
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
                f"Check for colliding role files in tools/agent_ops/roles/."
            )

        # [Bug #18] Validate llm_role exists in cfg.model_registry.
        # Without this, a typo like "cod" instead of "code" only fails at
        # llm.complete() runtime with a cryptic error. Warn at import.
        #
        # NOTE: This is a WARNING, not an error. Some roles are opt-in
        # (e.g., consultor is only in model_registry when CONSULTOR_MODEL
        # is set in .env). The dispatch code handles missing roles
        # gracefully at runtime with a clear error message. Failing here
        # would break every environment that doesn't have all optional
        # roles configured.
        llm_role = mod.ROLE_CONFIG.get("llm_role", "")
        if llm_role:
            try:
                from core.config import cfg
                if llm_role not in cfg.model_registry:
                    import sys as _sys
                    print(
                        f"[agent_ops] WARNING: Role '{role_name}' has llm_role='{llm_role}' "
                        f"which is not in cfg.model_registry. This is OK for opt-in roles "
                        f"(e.g., consultor when CONSULTOR_MODEL is unset), but may indicate "
                        f"a typo for required roles. Valid: {sorted(cfg.model_registry.keys())}.",
                        file=_sys.stderr,
                    )
            except ImportError:
                # cfg not available during partial imports (e.g., some test
                # harnesses) — skip validation, let it fail at runtime instead.
                pass

        ROLES[role_name] = {
            "system_prompt": mod.SYSTEM_PROMPT,
            "role_config": mod.ROLE_CONFIG,
        }
