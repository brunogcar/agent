"""Edit file action handler — MCP-style multi-edit."""

from __future__ import annotations

from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from core.config import cfg
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "edit_file",
    help_text="""Apply multiple line-based edits to a text file. Each edit replaces exact text.
Returns a git-style diff showing changes. Supports dry_run for preview.
Required: path, edits (list of {oldText, newText})
Optional: dry_run (default False) — preview without applying
Returns: {path, changes: [{oldText, newText, applied}], diff}""",
    examples=[
        'file(action="edit_file", path="app.py", edits=[{"oldText":"def old():","newText":"def new():"}], dry_run=True)',
    ],
)
def _handle_edit_file(
    path: str = "",
    edits: list[dict] | None = None,
    dry_run: bool = False,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Apply multiple line-based edits to a text file."""
    if not edits:
        return {"status": "error", "error": "edits list is required for edit_file"}

    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if cfg.is_protected(str(p)):
        return {"status": "error", "error": f"'{p}' is protected -- cannot edit"}
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}

    try:
        original = p.read_text(encoding="utf-8", errors="replace")
        content = original
        changes = []

        for edit in edits:
            old_text = edit.get("oldText", "")
            new_text = edit.get("newText", "")
            if not old_text:
                changes.append({"oldText": old_text, "newText": new_text, "applied": False, "error": "oldText is empty"})
                continue

            if old_text not in content:
                changes.append({"oldText": old_text, "newText": new_text, "applied": False, "error": "oldText not found"})
                continue

            if content.count(old_text) > 1:
                changes.append({"oldText": old_text, "newText": new_text, "applied": False, "error": "oldText appears multiple times — add surrounding context for uniqueness"})
                continue

            content = content.replace(old_text, new_text, 1)
            changes.append({"oldText": old_text, "newText": new_text, "applied": True})

        # Build diff
        orig_lines = original.splitlines()
        new_lines = content.splitlines()

        import difflib
        diff = "\n".join(difflib.unified_diff(
            orig_lines, new_lines,
            fromfile=str(p), tofile=str(p),
            lineterm=""
        ))

        if not dry_run:
            p.write_text(content, encoding="utf-8")

        return {
            "status": "success",
            "path": str(p),
            "changes": changes,
            "diff": diff,
            "dry_run": dry_run,
            "lines_changed": sum(1 for c in changes if c["applied"]),
        }
    except Exception as e:
        return {"status": "error", "error": f"Edit failed: {e}"}
