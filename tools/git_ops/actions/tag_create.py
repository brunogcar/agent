"""Tag create – create a lightweight tag.

Creates a lightweight tag at the current HEAD.
For annotated tags, use a future tag_annotate action.
Requires a valid git repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_TAG_CREATE = """
tag_create
Create a lightweight tag at current HEAD.
Required: target (tag name, e.g. "v1.0")
Optional: root
Returns: {status, tag, root}
"""

@register_action(
    "git", "tag_create",
    help_text=HELP_TAG_CREATE,
    needs_repo=True,
    examples=[
        'git(action="tag_create", target="v1.0")',
    ],
)
def run_tag_create(cwd, target: str = "", **kwargs) -> dict:
    """Create a lightweight tag."""
    if not target:
        return {"status": "error", "error": "target is required (tag name)"}
    code, _, err = _git(["tag", target], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    return {"status": "created", "tag": target, "root": str(cwd)}
