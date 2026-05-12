"""Checkout – switch branches or create a new one."""

from ._base import register_git
from ._helpers import _git, _check_repo

HELP_CHECKOUT = """\
checkout
    Switch to a branch or commit. Create and switch with '-b'.
    Use 'message' to specify target:
      - branch name        (e.g. checkout, message="main")
      - "-b new-branch"    (e.g. checkout, message="-b experiment")
"""

@register_git(
    name="checkout",
    help_text=HELP_CHECKOUT,
    needs_repo=True,
    examples=[
        "git(operation=\"checkout\", message=\"main\")          # switch",
        "git(operation=\"checkout\", message=\"-b new-idea\")   # create and switch",
    ],
)
def run_checkout(cwd, message: str = "", **kwargs) -> dict:
    target = message.strip() if message else ""
    if not target:
        return {"status": "error", "error": "Branch or commit to checkout is required (message param)"}

    if target.startswith("-b"):
        parts = target.split(maxsplit=1)
        if len(parts) < 2:
            return {"status": "error", "error": "Branch name required after -b"}
        branch_name = parts[1].strip()
        code, _, err = _git(["checkout", "-b", branch_name], cwd)
        if code != 0:
            return {"status": "error", "error": err}
        return {"status": "switched", "branch": branch_name, "root": str(cwd)}

    code, _, err = _git(["checkout", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "switched", "to": target, "root": str(cwd)}