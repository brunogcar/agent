"""List directory action handler."""

from __future__ import annotations

import time
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


@register_action(
    "file",
    "list_directory",
    help_text="""List contents of a directory with type, size, and modification time.
Required: path (directory)
Returns: {entries: [{name, type, size, modified, extension}], count}""",
    examples=[
        'file(action="list_directory", path=".")',
        'file(action="list_directory", path="tools")',
    ],
)
def _handle_list_directory(path: str = "", trace_id: str = "", **kwargs) -> dict:
    """List contents of a directory."""
    p, err = _safe_resolve(path or ".")
    if err:
        return {"status": "error", "error": err}
    if not p.is_dir():
        return {"status": "error", "error": f"Not a directory: {p}"}

    entries = []
    try:
        for item in sorted(p.iterdir()):
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else 0,
                "modified": time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)
                ),
                "extension": item.suffix if item.is_file() else "",
            })
    except PermissionError as e:
        return {"status": "error", "error": f"Permission denied: {e}"}

    return {
        "status": "success",
        "path": str(p),
        "entries": entries,
        "count": len(entries),
    }
