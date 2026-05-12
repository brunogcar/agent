"""Diff – show unstaged diff, optionally filtered by file."""

from pathlib import Path
from ._base import register_git
from ._helpers import _git

HELP_DIFF = """\
diff
    Unstaged diff. `path` filters to a specific file (relative or absolute).
    Optional: path (file to diff), root
    Returns: {diff, has_changes}
"""

@register_git(
    name="diff",
    help_text=HELP_DIFF,
    needs_repo=False,
    examples=[
        "git(operation=\"diff\")                          # all changes",
        "git(operation=\"diff\", path=\"tools/memory.py\") # specific file",
    ],
)
def run_diff(cwd, path: str = "", **kwargs) -> dict:
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