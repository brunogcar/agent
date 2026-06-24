"""Directory tree action handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


@register_action(
    "file",
    "directory_tree",
    help_text="""Get a recursive tree view of files and directories as structured JSON.
Useful for understanding project structure without reading every file.
Required: path
Optional: max_depth (default 5), exclude_patterns (list of glob patterns)
Returns: {tree: [{name, type, children?}], count}""",
    examples=[
        'file(action="directory_tree", path=".", max_depth=3)',
        'file(action="directory_tree", path="src", exclude_patterns=["__pycache__", "*.pyc"])',
    ],
)
def _handle_directory_tree(
    path: str = "",
    max_depth: int = 5,
    exclude_patterns: list[str] | None = None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Get a recursive tree view of files and directories."""
    p, err = _safe_resolve(path or ".")
    if err:
        return {"status": "error", "error": err}
    if not p.is_dir():
        return {"status": "error", "error": f"Not a directory: {p}"}

    exclude_patterns = exclude_patterns or []

    def _should_exclude(name: str, rel_path: str) -> bool:
        for pattern in exclude_patterns:
            import fnmatch
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return True
        # Always exclude hidden dirs and cache
        if name.startswith(".") or name == "__pycache__":
            return True
        return False

    def _build_tree(current: Path, depth: int, rel_prefix: str) -> list[dict[str, Any]]:
        if depth > max_depth:
            return []
        result = []
        try:
            for item in sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                rel = f"{rel_prefix}/{item.name}" if rel_prefix else item.name
                if _should_exclude(item.name, rel):
                    continue
                entry: dict[str, Any] = {
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                }
                if item.is_dir():
                    entry["children"] = _build_tree(item, depth + 1, rel)
                else:
                    try:
                        stat = item.stat()
                        entry["size"] = stat.st_size
                    except OSError:
                        pass
                result.append(entry)
        except PermissionError:
            pass
        return result

    tree = _build_tree(p, 1, "")

    def _count(entries: list) -> tuple[int, int]:
        files, dirs = 0, 0
        for e in entries:
            if e["type"] == "directory":
                dirs += 1
                cf, cd = _count(e.get("children", []))
                files += cf
                dirs += cd
            else:
                files += 1
        return files, dirs

    file_count, dir_count = _count(tree)

    return {
        "status": "success",
        "path": str(p),
        "tree": tree,
        "count": file_count + dir_count,
        "files": file_count,
        "directories": dir_count,
        "max_depth": max_depth,
    }
