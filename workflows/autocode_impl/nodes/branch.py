"""
Git branch node.

Creates a git branch before any code changes. The branch itself serves as
the safety net — no pre-snapshot is needed since changes are isolated on
the branch and can be reverted via git.

[v1.3] Optional pull before branching (AUTOCODE_PULL_BEFORE_BRANCH=1):
  When enabled, pulls recent commits from the remote before creating the
  branch. This ensures the branch is based on the latest remote state.
  Graceful-skip if GitHub is not configured.

# TODO(2.0): The FUTURE comment about pushing the branch + creating a draft
# PR is now implemented in node_publish (v1.3). This node stays focused on
# local branch creation only.

[v1.2] Removed unused `from typing import Any` import.
"""

from __future__ import annotations

from core.config import cfg
from workflows.autocode_impl.state import AutocodeState, _get_vcs  # [v2.1] accessor
from workflows.autocode_impl.vcs_ops import _git_create_branch
from workflows.autocode_impl.vcs_ops import _github_pull  # [v1.3]
from core.tracer import tracer

def node_git_branch(state: AutocodeState) -> dict:
    """Create git branch before any code changes.

    [Bug #2] Removed _git_snapshot call — the snapshot action was deleted
    from the git tool. The branch itself is the safety net. If something
    goes wrong, git revert on the branch recovers state.
    """
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return {}
    # [#47] Dry-run: skip branch creation. No git mutations in dry-run mode.
    if state.get("dry_run"):
        tracer.step(tid, "git_branch", "dry_run=True — skipping branch creation")
        return {}
    # [GIT SCOPING] Route git ops to workspace project if set, else agent_root
    root = state.get("project_root")

    # [v1.3] Optional: pull recent commits before branching
    # Ensures the branch is based on the latest remote state.
    # Graceful-skip if GitHub not configured or flag is off.
    if cfg.autocode_pull_before_branch:
        _github_pull(tid)  # Non-blocking — pull failure doesn't stop the workflow
        # TODO(2.0): Consider failing the workflow if pull fails (configurable)

    # Create branch (the branch IS the snapshot — no separate snapshot needed)
    # [P1 #10] Check return value — if branch creation fails, return error status
    # so the workflow doesn't continue writing to the wrong branch.
    # [v2.1] Use _get_vcs accessor (reads sub-state first, falls back to flat)
    branch = _get_vcs(state, "branch", "")
    if branch:
        success = _git_create_branch(branch, tid, root)
        if not success:
            return {
                "status": "error",
                "error": f"Failed to create git branch: {branch}",
            }

    return {}
