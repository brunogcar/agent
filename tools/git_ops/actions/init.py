"""
Init – initialise a new git repository with .gitignore and initial commit.

Creates a new repository, generates a sensible .gitignore, stages everything,
and makes an initial commit. Safely detects if the directory is already a repo.
Does not require needs_repo=True because it handles the check internally.
"""
from pathlib import Path
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git, _check_repo

HELP_INIT = """
init
Initialise a new git repository. Creates .gitignore + initial commit.
Call once when starting a new project folder. Errors if already a repo.
Optional: root
Returns: {status, path, commit_hash}
"""

@register_action(
    "git", "init",
    help_text=HELP_INIT,
    needs_repo=False,  # we check manually inside
    examples=[
        'git(action="init")                 # init in current agent root',
        'git(action="init", root="/path") # init elsewhere',
    ],
)
def run_init(cwd, **kwargs) -> dict:
    """Initialise a new git repository. Creates .gitignore + initial commit."""
    # Check if already a repo
    ok, _ = _check_repo(cwd)
    if ok:
        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {
            "status": "already_a_repo",
            "path": str(cwd),
            "head": head,
            "note": "Directory is already a git repository",
        }
    
    code, _, err = _git(["init"], cwd)
    if code != 0:
        return {"status": "error", "error": f"git init failed: {err}"}

    gi = cwd / ".gitignore"
    if not gi.exists():
        gi.write_text(
            "__pycache__/\n*.pyc\n*.pyo\n*.bak\n"
            ".env\nlogs/\n*.db\n*.lock\n",
            encoding="utf-8",
        )

    _git(["add", "-A"], cwd)
    code, _, err = _git(["commit", "-m", "initial commit"], cwd)
    if code != 0 and "nothing to commit" not in err:
        return {"status": "error", "error": f"Initial commit failed: {err}"}

    _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
    return {"status": "initialised", "path": str(cwd), "commit_hash": head}