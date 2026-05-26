"""
Commit – stage all + commit after successful changes.

Stages all tracked and untracked changes, then creates a commit.
Requires a valid git repository (validated by dispatcher via needs_repo=True).
Returns 'nothing_to_commit' if the working tree is already clean.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_COMMIT = """
commit
Stage all + commit. Call AFTER successful automated changes.
Required: message
Optional: root
Returns: {status: "committed"|"nothing_to_commit", commit_hash}
"""

@register_action(
    "git", "commit",
    help_text=HELP_COMMIT,
    needs_repo=True,
    examples=[
        'git(action="commit", message="fix: correct decay scoring")',
    ],
)
def run_commit(cwd, message: str = "", **kwargs) -> dict:
    if not message:
        return {"status": "error", "error": "message is required for commit"}

    _git(["add", "-A"], cwd)
    # Capture both stdout and stderr (Git version behavior varies)
    code, out, err = _git(["commit", "-m", message], cwd)
    if code != 0:
        if "nothing to commit" in (out + err):
            _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
            return {"status": "nothing_to_commit", "commit_hash": head}
        return {"status": "error", "error": err}

    _, hash_, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
    return {"status": "committed", "commit_hash": hash_, "root": str(cwd)}