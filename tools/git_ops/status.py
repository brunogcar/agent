"""Status – show working tree status."""

from ._base import register_git
from ._helpers import _git

HELP_STATUS = """\
status
    Working tree status. Tip: default root is agent.
    Optional: root
    Returns: {head, changes: [{flag, file}], clean, count}
"""

@register_git(
    name="status",
    help_text=HELP_STATUS,
    needs_repo=False,
    examples=[
        "git(operation=\"status\")         # agent repo",
        "git(operation=\"status\", root=\"workspace\")",
    ],
)
def run_status(cwd, **kwargs) -> dict:
    code, out, err = _git(["status", "--short"], cwd)
    if code != 0:
        return {"status": "error", "error": err}

    changes = []
    for line in out.splitlines():
        if len(line) >= 3:
            changes.append({"flag": line[:2].strip(), "file": line[3:]})

    _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
    return {
        "status": "ok",
        "head": head,
        "changes": changes,
        "clean": len(changes) == 0,
        "count": len(changes),
        "root": str(cwd),
    }