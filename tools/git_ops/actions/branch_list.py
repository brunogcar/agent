"""Branch list – list all local branches.

Read-only action that returns all local branches with current branch marker.
Does not require a valid git repository (git handles the error gracefully).
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git

HELP_BRANCH_LIST = """
branch_list
List all local branches. Marks the current branch.
Optional: root
Returns: {status, branches: [{name, current}], root}
"""

@register_action(
    "git", "branch_list",
    help_text=HELP_BRANCH_LIST,
    needs_repo=False,
    examples=[
        'git(action="branch_list")',
        'git(action="branch_list", root="workspace")',
    ],
)
def run_branch_list(cwd, **kwargs) -> dict:
    """List all local branches."""
    code, out, err = _git(["branch"], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    branches = []
    for line in out.splitlines():
        # git branch output: "* master" (current) or "  feature" (other)
        # The marker is "*" at position 0, followed by a space.
        # Non-current branches have two leading spaces.
        current = line.startswith("*")
        # Strip the "*" or leading spaces, then trim whitespace
        bname = line.lstrip("* ").strip()
        if bname:  # skip empty lines
            branches.append({"name": bname, "current": current})
    return {"status": "ok", "branches": branches, "root": str(cwd)}
