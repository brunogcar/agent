"""
Rollback – reset to HEAD, optionally with stash.

Resets the working tree to the latest commit. By default, stashes
uncommitted changes first so they can be recovered. If force=True,
permanently discards changes and cleans untracked files.
Requires a valid git repository.
"""
import time as _t
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_ROLLBACK = """
rollback
Reset to HEAD. Discards ALL uncommitted changes.
Default (force=False): stashes changes first (recoverable via git stash pop).
force=True: permanently discards changes + cleans untracked files.
Optional: root, force
Returns: {status, head, message, stash_ref}
"""

@register_action(
    "git", "rollback",
    help_text=HELP_ROLLBACK,
    needs_repo=True,
    examples=[
        'git(action="rollback")                # safe, auto stash',
        'git(action="rollback", force=True)    # permanent discard',
    ],
)
def run_rollback(cwd, force: bool = False, **kwargs) -> dict:
    """Reset to HEAD. Discards ALL uncommitted changes."""
    if force:
        _git(["reset", "--hard", "HEAD"], cwd)
        _git(["clean", "-fd"], cwd)
        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {
            "status": "rolled_back",
            "head": head,
            "message": "Force reset to HEAD (changes permanently discarded)",
            "root": str(cwd),
        }
    
    # safe path
    stash_msg = f"autocode-rollback-{int(_t.time())}"
    sr = _git(["stash", "push", "-m", stash_msg], cwd)
    stashed = "No local changes" not in sr[1]

    code, _, err = _git(["reset", "--hard", "HEAD"], cwd)
    if code != 0:
        return {"status": "error", "error": f"git reset failed: {err}"}

    _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
    msg = "Working tree reset to HEAD. "
    if stashed:
        msg += f"Changes saved to stash '{stash_msg}' -- run 'git stash pop' to restore."
    return {
        "status": "rolled_back",
        "head": head,
        "message": msg,
        "stash_ref": stash_msg if stashed else "",
        "root": str(cwd),
    }