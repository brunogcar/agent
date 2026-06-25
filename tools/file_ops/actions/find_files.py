"""Find files action handler — glob pattern matching."""

from __future__ import annotations

from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

MAX_RESULTS = 1000

@register_action(
    "file",
    "find_files",
    help_text="""Find files matching a glob pattern under a directory.
Required: pattern (glob, e.g. "**/*.py")
Optional: path (root directory, default ".")
Returns: {files: [{path, name, size}], count}""",
    examples=[
        'file(action="find_files", pattern="**/*.py", path=".")',
        'file(action="find_files", pattern="*.md", path="docs")',
    ],
)
def _handle_find_files(
    pattern: str = "",
    path: str = ".",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Find files matching a glob pattern."""
    if not pattern:
        return {"status": "error", "error": "pattern is required for find_files"}

    p, err = _safe_resolve(path or ".")
    if err:
        return {"status": "error", "error": err}
    if not p.is_dir():
        return {"status": "error", "error": f"Not a directory: {p}"}

    try:
        files = []
        for item in p.rglob(pattern):
            if item.is_file():
                try:
                    stat = item.stat()
                    files.append({
                        "path": str(item),
                        "name": item.name,
                        "size": stat.st_size,
                    })
                except OSError:
                    pass
                if len(files) >= MAX_RESULTS:
                    break

        return {
            "status": "success",
            "path": str(p),
            "pattern": pattern,
            "files": files,
            "count": len(files),
            "truncated": len(files) >= MAX_RESULTS,
        }
    except Exception as e:
        return {"status": "error", "error": f"Find failed: {e}"}
