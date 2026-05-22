"""
Patch (str_replace) action handler.
"""

from __future__ import annotations

from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from core.config import cfg
from tools.file_ops._registry import register_action

@register_action("file", "patch")
def _handle_patch(path: str = "", **kwargs) -> dict:
    """
    Apply a targeted str_replace patch.
    old must appear EXACTLY ONCE -- add surrounding lines for uniqueness.
    """
    old_text = kwargs.get("old", "")
    new_text = kwargs.get("new", "")
    if not old_text:
        return {"status": "error", "error": "patch requires 'old' parameter"}

    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if cfg.is_protected(path):
        return {"status": "error",
                "error": f"'{path}' is protected -- cannot patch"}

    from core.patch import apply_patch
    result = apply_patch(p, old_text, new_text)
    if result.ok:
        return {
            "status": "success",
            "path": result.path,
            "lines_changed": result.lines_changed,
            "backup_path": result.backup_path,
        }
    else:
        return {"status": "error", "error": result.error}