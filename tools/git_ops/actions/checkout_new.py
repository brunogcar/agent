"""Checkout new – create and switch to a new branch.

Creates a new branch at the current HEAD and immediately switches to it.
Equivalent to `git checkout -b <name>`.
Requires a valid git repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_CHECKOUT_NEW = """
checkout_new
Create and switch to a new branch. Equivalent to `git checkout -b`.
Required: target (new branch name)
Optional: root
Returns: {status, branch, root}
"""

@register_action(
    "git", "checkout_new",
    help_text=HELP_CHECKOUT_NEW,
    needs_repo=True,
    examples=[
        'git(action="checkout_new", target="feature-x")',
    ],
)
def run_checkout_new(cwd, target: str = "", **kwargs) -> dict:
    """Create and switch to a new branch."""
    if not target:
        return {"status": "error", "error": "target is required (new branch name)"}
    code, _, err = _git(["checkout", "-b", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "switched", "branch": target, "root": str(cwd)}
