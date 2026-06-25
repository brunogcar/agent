"""Create directory action handler."""

from __future__ import annotations

from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "create_directory",
    help_text="""Create a new directory or ensure it exists. Creates nested directories.
Required: path
Optional: parents (default True) — create parent directories if needed
Returns: {path, created}""",
    examples=[
        'file(action="create_directory", path="tmp/new_folder")',
        'file(action="create_directory", path="a/b/c", parents=True)',
    ],
)
def _handle_create_directory(path: str = "", parents: bool = True, trace_id: str = "", **kwargs) -> dict:
    """Create a new directory or ensure it exists."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}

    try:
        was_new = not p.exists()
        if parents:
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.mkdir(parents=False, exist_ok=True)
        return {
            "status": "success",
            "path": str(p),
            "created": was_new,
        }
    except FileNotFoundError:
        return {"status": "error", "error": f"Parent directory does not exist: {p.parent}"}
    except Exception as e:
        return {"status": "error", "error": f"Create directory failed: {e}"}
