# tools/git_ops/show.py

"""Show details of a commit, tag, or tree object."""

from ._base import register_git
from ._helpers import _git

# ── Help block (appears in the main tool's docstring) ──
HELP_SHOW = """\
show
    Show details of a commit, tag, or tree object.
    'message' = commit hash, tag name (default: "HEAD")
    Returns: {status, output (capped at 10KB), ...}
"""

# ── Register the handler ──
@register_git(
    name="show",
    help_text=HELP_SHOW,
    needs_repo=False,                       # read‑only – no repo check needed
    examples=[
        "git(operation=\"show\")                      # latest commit",
        "git(operation=\"show\", message=\"abc1234\")  # specific commit",
        "git(operation=\"show\", message=\"v1.0\")     # show a tag",
    ],
)
def run_show(cwd, message: str = "", **kwargs) -> dict:
    """Actual implementation."""
    target = message.strip() if message.strip() else "HEAD"
    code, out, err = _git(["show", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "ok", "output": out[:10_000], "root": str(cwd)}