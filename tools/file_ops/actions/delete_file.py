"""Delete file action handler."""

from __future__ import annotations

import shutil
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


@register_action(
    "file",
    "delete_file",
    help_text="""Delete a file or directory. Destructive — requires force=True.
Required: path
Optional: recursive (default False) — remove directory and all contents
Returns: {path, deleted}""",
    examples=[
        'file(action="delete_file", path="tmp/old.txt", force=True)',
        'file(action="delete_file", path="tmp/empty_dir", force=True, recursive=True)',
    ],
)
def _handle_delete_file(
    path: str = "",
    force: bool = False,
    recursive: bool = False,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Delete a file or directory."""
    if not force:
        return {
            "status": "error",
            "error": "delete_file is destructive. Set force=True to confirm.",
        }

    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p.exists():
        return {"status": "error", "error": f"Path not found: {p}"}

    try:
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                # Only delete if empty
                try:
                    p.rmdir()
                except OSError:
                    return {
                        "status": "error",
                        "error": f"Directory not empty: {p}. Use recursive=True to remove contents.",
                    }
        else:
            p.unlink()

        return {
            "status": "success",
            "path": str(p),
            "deleted": True,
        }
    except Exception as e:
        return {"status": "error", "error": f"Delete failed: {e}"}
