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
Optional: path (file to diff), max_lines (default 500), root
Returns: {diff, has_changes, truncated, total_lines}
"""

@register_action(
    "git", "diff",
    help_text=HELP_DIFF,
    needs_repo=False,
    examples=[
        'git(operation="diff")                                      # all changes',
        'git(operation="diff", path="tools/memory.py")              # specific file',
        'git(operation="diff", max_lines=1000)                      # allow larger diff',
    ],
)
def run_diff(cwd, path: str = "", max_lines: int = 500, **kwargs) -> dict:
    """
    Unstaged diff. `path` filters to a specific file (relative or absolute).
    `max_lines` truncates the output to prevent LLM context window overflow.
    """
    args = ["diff"]
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = cwd / path
        args.append(str(p))

    code, out, err = _git(args, cwd)
    if code != 0:
        return {"status": "error", "error": err}

    if not out:
        return {
            "status": "ok",
            "diff": "",
            "has_changes": False,
            "truncated": False,
            "total_lines": 0,
            "root": str(cwd),
        }

    # ── P2-4: Line-based Truncation ─────────────────────────────────────
    lines = out.split("\n")
    total_lines = len(lines)
    truncated = total_lines > max_lines

    if truncated:
        diff_output = "\n".join(lines[:max_lines])
        diff_output += f"\n\n... [Diff truncated: {total_lines} lines total, showing first {max_lines}. Use file-specific diffs for details.]"
    else:
        diff_output = out

    return {
        "status": "ok",
        "diff": diff_output,
        "has_changes": True,
        "truncated": truncated,
        "total_lines": total_lines,
        "max_lines": max_lines,
        "root": str(cwd),
    }