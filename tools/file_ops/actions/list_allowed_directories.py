"""List allowed directories action handler."""

from __future__ import annotations

from tools.file_ops.helpers import _allowed_roots
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
    """Return allowed roots from path_guard."""
    roots = _allowed_roots()
    return {
        "status": "success",
        "roots": [
            {"path": str(r), "name": r.name}
            for r in roots
        ],
        "count": len(roots),
    }
