"""Tag delete – delete a local tag.

Removes a lightweight tag from the local repository.
Requires a valid git repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_TAG_DELETE = """
tag_delete
Delete a local tag.
Required: target (tag name)
Optional: root
Returns: {status, tag, root}
"""

@register_action(
    "git", "tag_delete",
    help_text=HELP_TAG_DELETE,
    needs_repo=True,
    examples=[
        'git(action="tag_delete", target="v0.9")',
    ],
)
def run_tag_delete(cwd, target: str = "", **kwargs) -> dict:
    """Delete a local tag."""
    if not target:
        return {"status": "error", "error": "target is required (tag name)"}
    code, _, err = _git(["tag", "-d", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "deleted", "tag": target, "root": str(cwd)}
