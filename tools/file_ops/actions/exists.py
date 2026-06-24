"""Exists action handler."""

from __future__ import annotations

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


@register_action(
    "file",
    "exists",
    help_text="""Check if a path exists and is accessible.
Required: path
Returns: {exists, type}""",
    examples=[
        'file(action="exists", path="tools/file.py")',
    ],
)
def _handle_exists(path: str = "", trace_id: str = "", **kwargs) -> dict:
    """Check if a path exists."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "success", "exists": False, "error": err}

    exists = p.exists()
    result = {
        "status": "success",
        "exists": exists,
        "path": str(p),
    }
    if exists:
        result["type"] = "directory" if p.is_dir() else "file"
    return result
