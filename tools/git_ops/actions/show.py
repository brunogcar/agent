"""
Show – details of a commit, tag, or tree object.

Read-only operation that displays the contents and metadata of a git object.
Defaults to HEAD if no reference is provided via the `message` parameter.
Output is capped at 10KB to prevent LLM context overflow.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git

HELP_SHOW = """
show
Show details of a commit, tag, or tree object.
'message' = commit hash, tag name (default: "HEAD")
Returns: {status, output (capped at 10KB), ...}
"""

@register_action(
    "git", "show",
    help_text=HELP_SHOW,
    needs_repo=False,  # read-only – no repo check needed
    examples=[
        'git(operation="show")                      # latest commit',
        'git(operation="show", message="abc1234")  # specific commit',
        'git(operation="show", message="v1.0")     # show a tag',
    ],
)
def run_show(cwd, message: str = "", **kwargs) -> dict:
    """Show details of a commit, tag, or tree object."""
    target = message.strip() if message.strip() else "HEAD"
    code, out, err = _git(["show", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "ok", "output": out[:10_000], "root": str(cwd)}