"""
Tag – list or create lightweight tags.

Manages lightweight tags to mark milestones or releases.
Subcommands are passed via the `message` parameter:
  - list (default)
  - create <name>
Only the 'create' subcommand requires a valid repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_TAG = """
tag
List or create lightweight tags to mark milestones.
Subcommands (via 'message'):
- list              (default)
- create <name>     (e.g. message="create v1.0")
"""

@register_action(
    "git", "tag",
    help_text=HELP_TAG,
    needs_repo=False,  # only create needs check, handled inside
    examples=[
        'git(action="tag")                          # list',
        'git(action="tag", message="create v1.0")  # create',
    ],
)
def run_tag(cwd, message: str = "", **kwargs) -> dict:
    """List or create lightweight tags to mark milestones."""
    parts = message.strip().split(maxsplit=1) if message.strip() else []
    sub = parts[0].lower() if parts else "list"
    name = parts[1] if len(parts) > 1 else ""
    
    if sub == "list":
        code, out, err = _git(["tag", "-l"], cwd)
        if code != 0:
            return {"status": "error", "error": err}
        tags = [t.strip() for t in out.splitlines() if t.strip()]
        return {"status": "ok", "tags": tags, "root": str(cwd)}

    elif sub == "create":
        if not name:
            return {"status": "error", "error": "Tag name required (message='create <name>')"}
        ok, err = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err}
        code, _, err = _git(["tag", name], cwd)
        if code != 0:
            return {"status": "error", "error": err}
        return {"status": "created", "tag": name, "root": str(cwd)}

    else:
        return {"status": "error", "error": f"Unknown tag subcommand: '{sub}'. Use list, create <name>"}