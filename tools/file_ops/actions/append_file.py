"""Append file action handler."""

from __future__ import annotations

from pathlib import Path

from core.config import cfg
from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "append_file",
    help_text="""Append content to a file. Creates file if it does not exist.
Required: path, content
Returns: {path, size, lines_appended}""",
    examples=[
        'file(action="append_file", path="logs/app.log", content="New log line\n")',
    ],
)
def _handle_append_file(path: str = "", content: str = "", **kwargs) -> dict:
    """Append content to a file. Creates file if not exists."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if content is None:
        return {"status": "error", "error": "content is required for append_file"}
    if cfg.is_protected(p):
        return {"status": "error", "error": f"'{p.name}' is protected — edit manually"}

    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return {
            "status": "success",
            "path": str(p),
            "size": p.stat().st_size,
            "lines_appended": content.count("\n") + (1 if content and not content.endswith("\n") else 0),
        }
    except Exception as e:
        return {"status": "error", "error": f"Append failed: {e}"}
