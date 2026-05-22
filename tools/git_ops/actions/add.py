"""
Add – stage files for commit.

Stages specific files/directories or all changes. Integrates safely with
the dispatcher's path resolution and repo validation.
"""
from pathlib import Path
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_ADD = """
add
Stage files for commit.
Optional: path (specific file/dir to stage), all_files (bool, default False)
If path is provided, stages that target. If all_files=True, stages everything.
Returns: {status, target, staged_files, count, root}
"""

@register_action(
    "git", "add",
    help_text=HELP_ADD,
    needs_repo=True,
    examples=[
        'git(operation="add", path="src/main.py")      # stage specific file',
        'git(operation="add", all_files=True)          # stage all changes',
    ],
)
def run_add(cwd, path: str = "", all_files: bool = False, **kwargs) -> dict:
    """Stage files for commit."""
    args = ["add"]
    staged_target = ""

    if all_files:
        args.append("-A")
        staged_target = "all"
    elif path:
        p = Path(path)
        if not p.is_absolute():
            p = cwd / path
        args.append(str(p))
        staged_target = str(p)
    else:
        # Default: stage current directory
        args.append(".")
        staged_target = "."

    code, _, err = _git(args, cwd)
    if code != 0:
        return {"status": "error", "error": err}

    # Verify what was actually staged
    _, porcelain, _ = _git(["status", "--porcelain"], cwd)
    staged_files = []
    if porcelain:
        for line in porcelain.splitlines():
            if len(line) >= 3 and line[0] in ("M", "A", "R", "C", "D"):
                staged_files.append(line[3:].strip())

    return {
        "status": "ok",
        "target": staged_target,
        "staged_files": staged_files,
        "count": len(staged_files),
        "root": str(cwd),
    }