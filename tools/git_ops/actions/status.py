"""
Status – show working tree status.

Returns structured working tree state: branch, changes list, clean flag.
Read-only operation; does not require a valid git repository to run
(will gracefully report if not a repo via git's own output).
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git

HELP_STATUS = """
status
Working tree status. Tip: default root is agent.
Optional: root
Returns: {head, changes: [{flag, file}], clean, count}
"""

@register_action(
    "git", "status",
    help_text=HELP_STATUS,
    needs_repo=False,
    examples=[
        'git(operation="status")         # agent repo',
        'git(operation="status", root="workspace")',
    ],
)
def run_status(cwd, **kwargs) -> dict:
    """Show working tree status. Tip: default root is agent."""
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