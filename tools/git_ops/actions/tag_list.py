"""Tag list – list all lightweight tags.

Read-only action that returns all tags in the repository.
Does not require a valid git repository.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git

HELP_TAG_LIST = """
tag_list
List all lightweight tags.
Optional: root
Returns: {status, tags: [...], root}
"""

@register_action(
    "git", "tag_list",
    help_text=HELP_TAG_LIST,
    needs_repo=False,
    examples=[
        'git(action="tag_list")',
    ],
)
def run_tag_list(cwd, **kwargs) -> dict:
    """List all lightweight tags."""
    code, out, err = _git(["tag", "-l"], cwd)
    if code != 0:
        return {"status": "error", "error": err}
    tags = [t.strip() for t in out.splitlines() if t.strip()]
    return {"status": "ok", "tags": tags, "root": str(cwd)}
