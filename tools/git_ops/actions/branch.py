"""
Branch – list, create, or delete local branches.

Manages local branches. Subcommands are passed via the `message` parameter:
  - list (default)
  - create <name>
  - delete <name> (safe delete, only if merged)
Only create/delete require a valid repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_BRANCH = """
branch
Manage local branches. Subcommands (via 'message'):
- list              (no message or message="list")
- create <name>     (message="create my-branch")
- delete <name>     (message="delete old-branch") – safe, only if merged
"""

@register_action(
    "git", "branch",
    help_text=HELP_BRANCH,
    needs_repo=False,  # handlers check for write ops internally
    examples=[
        'git(action="branch")                              # list',
        'git(action="branch", message="create experiment") # create',
        'git(action="branch", message="delete old-fix")    # delete',
    ],
)
def run_branch(cwd, message: str = "", **kwargs) -> dict:
    """Manage local branches. Subcommands via 'message'."""
    parts = message.strip().split(maxsplit=1) if message.strip() else []
    sub = parts[0].lower() if parts else "list"
    name = parts[1] if len(parts) > 1 else ""
    
    if sub == "list":
        code, out, err = _git(["branch"], cwd)
        if code != 0:
            return {"status": "error", "error": err}
        branches = []
        for line in out.splitlines():
            current = line.startswith("* ")
            bname = line[2:].strip()
            branches.append({"name": bname, "current": current})
        return {"status": "ok", "branches": branches, "root": str(cwd)}

    elif sub == "create":
        if not name:
            return {"status": "error", "error": "Branch name required (message='create <name>')"}
        ok, err = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err}
        code, _, err = _git(["branch", name], cwd)
        if code != 0:
            return {"status": "error", "error": err}
        return {"status": "created", "branch": name, "root": str(cwd)}

    elif sub == "delete":
        if not name:
            return {"status": "error", "error": "Branch name required (message='delete <name>')"}
        ok, err = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err}
        code, _, err = _git(["branch", "-d", name], cwd)
        if code != 0:
            return {"status": "error", "error": err}
        return {"status": "deleted", "branch": name, "root": str(cwd)}

    else:
        return {"status": "error", "error": f"Unknown branch subcommand: '{sub}'. Use list, create <name>, delete <name>"}