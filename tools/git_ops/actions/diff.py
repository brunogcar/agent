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
    Unstaged diff.  `path`  filters to a specific file (relative or absolute).
    `max_lines`  truncates the output to prevent LLM context window overflow.
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

    # ── P1-2: Smart Truncation ──────────────────────────────────────────────
    lines = out.splitlines()
    total_lines = len(lines)
    truncated = total_lines > max_lines

    if truncated:
        critical_keywords = {"diff --git", "@@", "error:", "fatal:", "traceback", "exception"}
        critical_indices = {i for i, line in enumerate(lines) 
                           if any(kw in line.lower() for kw in critical_keywords)}
        
        header_end = next((i for i, line in enumerate(lines) 
                           if line.startswith("@@") or line.startswith("diff --git")), 10)
        keep_start = min(int(max_lines * 0.25) + header_end, total_lines // 2)
        keep_end = min(int(max_lines * 0.25) + 10, total_lines // 2)
        
        result = []
        seen_indices = set()
        for i in range(keep_start):
            result.append(lines[i])
            seen_indices.add(i)
        for i in sorted(critical_indices):
            if keep_start <= i < total_lines - keep_end:
                result.append(lines[i])
                seen_indices.add(i)
        for i in range(total_lines - keep_end, total_lines):
            if i not in seen_indices:
                result.append(lines[i])
        
        diff_output = "\n".join(result)
        diff_output += f"\n\n... [Diff truncated: {total_lines} lines total, showing {len(result)} lines (preserving headers & errors).]"
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