"""List allowed directories action handler.

v1.1: Updated to use core.config.cfg directly instead of the removed
_allowed_roots() from helpers.py. This ensures consistency with core.path_guard
which validates against these same roots.
"""

from __future__ import annotations

from core.config import cfg
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "list_allowed_directories",
    help_text="""Return the list of directories the file tool is allowed to access.
Useful for discovering available paths before attempting file operations.
No parameters required.
Returns: {roots: [{path, name}]}""",
    examples=[
        'file(action="list_allowed_directories")',
    ],
)
def _handle_list_allowed_directories(trace_id: str = "", **kwargs) -> dict:
    """Return allowed roots.

    Returns the agent_root and workspace_root from core.config.cfg.
    These are the same roots used by core.path_guard for path validation.
    """
    roots = [cfg.agent_root.resolve(), cfg.workspace_root.resolve()]
    return {
        "status": "success",
        "roots": [
            {"path": str(r), "name": r.name}
            for r in roots
        ],
        "count": len(roots),
    }
