"""Checkout branch – switch to an existing branch or commit.

Switches the working tree to an existing branch, tag, or commit hash.
Requires a valid git repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_CHECKOUT_BRANCH = """
checkout_branch
Switch to an existing branch, tag, or commit.
Required: target (branch name, tag, or commit hash)
Optional: root
Returns: {status, to, root}
"""

@register_action(
    "git", "checkout_branch",
    help_text=HELP_CHECKOUT_BRANCH,
    needs_repo=True,
    examples=[
        'git(action="checkout_branch", target="main")',
        'git(action="checkout_branch", target="v1.0")',
        'git(action="checkout_branch", target="abc1234")',
    ],
)
def run_checkout_branch(cwd, target: str = "", **kwargs) -> dict:
    """Switch to an existing branch or commit."""
    if not target:
        return {"status": "error", "error": "target is required (branch name, tag, or commit hash)"}
    code, _, err = _git(["checkout", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "switched", "to": target, "root": str(cwd)}
