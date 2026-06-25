"""Clone action handler.

Clones a remote git repository into the workspace directory.
This is a WORKSPACE_ROOT-only operation.

INTEGRATION NOTE:
  The facade (tools/git.py) resolves the cwd to workspace_root for clone actions.
  This handler validates the derived local directory path and executes the clone.
"""
from __future__ import annotations

from pathlib import Path

from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git
from core.config import cfg

HELP_CLONE = """
clone
Clone a remote repository into a local directory within WORKSPACE_ROOT.
Required: target (remote URL, e.g. "https://github.com/user/repo.git")
Optional: path (local directory name, defaults to repo name from URL)
Returns: {status: "cloned", path, url, root}
"""

@register_action(
    "git", "clone",
    help_text=HELP_CLONE,
    needs_repo=False,
    examples=[
        'git(action="clone", target="https://github.com/user/repo.git")',
        'git(action="clone", target="https://github.com/user/repo.git", path="my_folder")',
    ],
)
def run_clone(cwd, target: str = "", path: str = "", **kwargs) -> dict:
    """Clone a remote repository into WORKSPACE_ROOT."""
    if not target:
        return {"status": "error", "error": "target is required (remote URL)"}

    # Derive local directory name from URL if not explicitly provided
    clone_target = path or target.rstrip("/").split("/")[-1].replace(".git", "")
    if not clone_target:
        return {"status": "error", "error": "Could not determine clone target directory from URL"}

    # Resolve target path within workspace
    target_path = Path(cwd) / clone_target
    target_path = target_path.resolve()

    # Prevent overwriting existing directories
    if target_path.exists():
        return {"status": "error", "error": f"Directory already exists: {target_path}"}

    # Execute clone
    code, out, err = _git(["clone", target, str(target_path)], Path(cwd))
    if code != 0:
        return {"status": "error", "error": err or "Clone failed"}

    return {
        "status": "cloned",
        "path": str(target_path),
        "url": target,
        "root": str(Path(cwd)),
    }
