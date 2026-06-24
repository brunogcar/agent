"""Branch delete – safely delete a merged local branch.

Deletes a local branch only if it has been fully merged.
Use force=True to delete unmerged branches (destructive).
Requires a valid git repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_BRANCH_DELETE = """
branch_delete
Safely delete a merged local branch.
Required: target (branch name)
Optional: force (default False), root
Returns: {status, branch, root}
"""

@register_action(
    "git", "branch_delete",
    help_text=HELP_BRANCH_DELETE,
    needs_repo=True,
    examples=[
        'git(action="branch_delete", target="old-fix")',
        'git(action="branch_delete", target="wip", force=True)',
    ],
)
def run_branch_delete(cwd, target: str = "", force: bool = False, **kwargs) -> dict:
    """Safely delete a merged local branch."""
    if not target:
        return {"status": "error", "error": "target is required (branch name)"}
    args = ["branch", "-d" if not force else "-D", target]
    code, _, err = _git(args, cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "deleted", "branch": target, "root": str(cwd)}
