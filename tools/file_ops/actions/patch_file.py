"""Patch (str_replace) action handler."""

from __future__ import annotations

from pathlib import Path

from core.path_guard import check_protected_file
from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "patch_file",
    help_text="""Apply a targeted str_replace patch. old must appear EXACTLY ONCE.
Add surrounding lines for uniqueness. Uses workflows/autocode_helpers/patch.
Required: path, old, new
Returns: {path, lines_changed}""",
    examples=[
        'file(action="patch_file", path="app.py", old="def old():", new="def new():")',
    ],
)
def _handle_patch_file(path: str = "", **kwargs) -> dict:
    """
    Apply a targeted str_replace patch.
    old must appear EXACTLY ONCE -- add surrounding lines for uniqueness.
    """
    old_text = kwargs.get("old", "")
    new_text = kwargs.get("new", "")
    if not old_text:
        return {"status": "error", "error": "patch_file requires 'old' parameter"}

    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}

    # v1.1: Use centralized check_protected_file instead of direct cfg.is_protected()
    allowed, err = check_protected_file(p, "patch_file")
    if not allowed:
        return {"status": "error", "error": err}

    from workflows.autocode_helpers.patch import apply_patch
    result = apply_patch(p, old_text, new_text)
    if result.ok:
        return {
            "status": "success",
            "path": result.path,
            "lines_changed": result.lines_changed,
        }
    else:
        return {"status": "error", "error": result.error}
