"""
Snapshot – stage all + timestamped commit as a safe rollback point.

Creates a safe checkpoint before automated changes. Stages everything,
checks if there are actual changes, and commits with a timestamped message.
Returns 'nothing_to_commit' if the tree is already clean.
Requires a valid git repository.
"""
from datetime import datetime
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_SNAPSHOT = """
snapshot
Stage all + timestamped commit. Call BEFORE automated changes.
Creates a safe rollback point. Returns nothing_to_commit if tree is clean.
Optional: message (appended to timestamp), root
Returns: {status: "committed"|"nothing_to_commit", commit_hash, message}
"""

@register_action(
    "git", "snapshot",
    help_text=HELP_SNAPSHOT,
    needs_repo=True,
    examples=[
        'git(operation="snapshot")                      # auto timestamp only',
        'git(operation="snapshot", message="before edit") # with custom note',
    ],
)
def run_snapshot(cwd, message: str = "", **kwargs) -> dict:
    """Stage all + timestamped commit. Call BEFORE automated changes."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    full_msg = f"snapshot [{ts}]" + (f": {message}" if message else "")
    _git(["add", "-A"], cwd)

    # Check if there's anything to commit AFTER staging
    _, porcelain, _ = _git(["status", "--porcelain"], cwd)
    if not porcelain:
        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {
            "status": "nothing_to_commit",
            "commit_hash": head,
            "message": full_msg,
            "root": str(cwd),
        }

    code, _, err = _git(["commit", "-m", full_msg], cwd)
    if code != 0:
        return {"status": "error", "error": f"Snapshot commit failed: {err}"}

    _, hash_, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
    return {"status": "committed", "commit_hash": hash_, "message": full_msg, "root": str(cwd)}