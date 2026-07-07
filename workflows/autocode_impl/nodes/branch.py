"""
Git branch node.

Creates a git branch before any code changes. The branch itself serves as
the safety net — no pre-snapshot is needed since changes are isolated on
the branch and can be reverted via git.

[FUTURE] When GitHub PR integration is added, this node will also push
the branch to the remote and create a draft PR. For now, local branch only.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.git_ops import _git_create_branch
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

    # Create branch (the branch IS the snapshot — no separate snapshot needed)
    # [P1 #10] Check return value — if branch creation fails, return error status
    # so the workflow doesn't continue writing to the wrong branch.
    if state.get("branch"):
        success = _git_create_branch(state["branch"], tid, root)
        if not success:
            return {
                "status": "error",
                "error": f"Failed to create git branch: {state['branch']}",
            }

    return {}
