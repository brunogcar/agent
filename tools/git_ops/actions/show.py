"""Show – details of a commit, tag, or tree object.

Read-only action that displays the contents and metadata of a git object.
Defaults to HEAD if no reference is provided via the `target` parameter.
Output is capped at 10KB to prevent LLM context overflow.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git

HELP_SHOW = """
show
Show details of a commit, tag, or tree object.
'target' = commit hash, tag name (default: "HEAD")
Returns: {status, output (capped at 10KB), ...}
"""

@register_action(
    "git", "show",
    help_text=HELP_SHOW,
    needs_repo=False,  # read-only – no repo check needed
    examples=[
        'git(action="show")                    # latest commit',
        'git(action="show", target="abc1234")  # specific commit',
        'git(action="show", target="v1.0")     # show a tag',
    ],
)
def run_show(cwd, target: str = "", **kwargs) -> dict:
    """Show details of a commit, tag, or tree object."""
    ref = target.strip() if target.strip() else "HEAD"
    code, out, err = _git(["show", ref], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "ok", "output": out[:10_000], "root": str(cwd)}
