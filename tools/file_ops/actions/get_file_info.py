"""Get file info action handler."""

from __future__ import annotations

import time
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


@register_action(
    "file",
    "get_file_info",
    help_text="""Retrieve detailed metadata about a file or directory.
Returns size, type, permissions, creation time, modification time.
Required: path
Returns: {path, type, size, mode, created, modified, is_file, is_dir, is_symlink}""",
    examples=[
        'file(action="get_file_info", path="tools/file.py")',
    ],
)
def _handle_get_file_info(path: str = "", trace_id: str = "", **kwargs) -> dict:
    """Retrieve detailed metadata about a file or directory."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p.exists():
        return {"status": "error", "error": f"Path not found: {p}"}

    try:
        stat = p.stat()
        return {
            "status": "success",
            "path": str(p),
            "name": p.name,
            "type": "directory" if p.is_dir() else "file",
            "size": stat.st_size,
            "mode": oct(stat.st_mode)[-3:],
            "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_ctime)),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            "accessed": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_atime)),
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "is_symlink": p.is_symlink(),
            "extension": p.suffix if p.is_file() else "",
            "parent": str(p.parent),
        }
    except Exception as e:
        return {"status": "error", "error": f"Get file info failed: {e}"}
