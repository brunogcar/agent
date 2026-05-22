"""
Diff – show unstaged diff, optionally filtered by file.

Returns unified diff output for unstaged changes. The `path` parameter
filters the diff to a specific file (relative or absolute).
Read-only operation.
"""
from pathlib import Path
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git

HELP_DIFF = """
diff
Unstaged diff. `path` filters to a specific file (relative or absolute).
Optional: path (file to diff), root
Returns: {diff, has_changes}
"""

@register_action(
    "git", "diff",
    help_text=HELP_DIFF,
    needs_repo=False,
    examples=[
        'git(operation="diff")                          # all changes',
        'git(operation="diff", path="tools/memory.py") # specific file',
    ],
)
def run_diff(cwd, path: str = "", **kwargs) -> dict:
    """Unstaged diff. `path` filters to a specific file (relative or absolute)."""
    args = ["diff"]
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = cwd / path
        args.append(str(p))
    
    code, out, err = _git(args, cwd)
    if code != 0:
        return {"status": "error", "error": err}

    return {
        "status": "ok",
        "diff": out[:10_000] if out else "",
        "has_changes": bool(out),
        "root": str(cwd),
    }