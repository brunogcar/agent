"""Write file action handler."""

from __future__ import annotations

from pathlib import Path

from core.path_guard import check_protected_file
from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "write_file",
    help_text="""Write content to a file. Auto-creates parent directories.
Required: path, content
Returns: {path, size, lines}""",
    examples=[
        'file(action="write_file", path="output/report.md", content="# Report\n...")',
    ],
)
def _handle_write_file(path: str = "", content: str = "", **kwargs) -> dict:
    """Write content to a file. Auto-creates parent directories."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if content is None:
        return {"status": "error", "error": "content is required for write_file"}

    # v1.1: Use centralized check_protected_file instead of direct cfg.is_protected()
    # This ensures the action is classified in WRITE_OPERATIONS and gets consistent error messages.
    allowed, err = check_protected_file(p, "write_file")
    if not allowed:
        return {"status": "error", "error": err}

    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        p.write_text(content, encoding="utf-8")
        return {
            "status": "success",
            "path": str(p),
            "size": len(content.encode("utf-8")),
            "lines": content.count("\n") + 1,
        }
    except Exception as e:
        return {"status": "error", "error": f"Write failed: {e}"}
