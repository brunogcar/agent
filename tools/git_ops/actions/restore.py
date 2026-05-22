"""
Restore – restore a specific file to HEAD or a specified commit.

Discards local changes to a single file. Optionally restores from a
specific commit ref via the `message` parameter.
Requires a valid git repository.
"""
from pathlib import Path
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_RESTORE = """
restore
Restore a specific file to HEAD (or a specified commit) discarding local changes.
'path' parameter = file to restore (relative or absolute)
'message' parameter = optional commit ref (e.g. "HEAD~2")
"""

@register_action(
    "git", "restore",
    help_text=HELP_RESTORE,
    needs_repo=True,
    examples=[
        'git(operation="restore", path="tools/git_ops.py")',
        'git(operation="restore", path="README.md", message="HEAD~2")',
    ],
)
def run_restore(cwd, path: str = "", message: str = "", **kwargs) -> dict:
    """Restore a specific file to HEAD (or a specified commit)."""
    if not path:
        return {"status": "error", "error": "File path is required (use the 'path' parameter)"}
    
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = cwd / path

    args = ["restore"]
    if message.strip():
        args.append(f"--source={message.strip()}")
    args.append(str(file_path))

    code, _, err = _git(args, cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "restored", "file": str(file_path), "root": str(cwd)}