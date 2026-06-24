"""Branch create – create a new local branch.

Creates a new branch pointer at the current HEAD. Does NOT switch to it.
Use checkout_new to create and switch in one step.
Requires a valid git repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_BRANCH_CREATE = """
branch_create
Create a new local branch at current HEAD. Does NOT switch to it.
Required: target (branch name)
Optional: root
Returns: {status, branch, root}
"""

@register_action(
    "git", "branch_create",
    help_text=HELP_BRANCH_CREATE,
    needs_repo=True,
    examples=[
        'git(action="branch_create", target="experiment")',
    ],
)
def run_branch_create(cwd, target: str = "", **kwargs) -> dict:
    """Create a new local branch."""
    if not target:
        return {"status": "error", "error": "target is required (branch name)"}
    code, _, err = _git(["branch", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "created", "branch": target, "root": str(cwd)}
