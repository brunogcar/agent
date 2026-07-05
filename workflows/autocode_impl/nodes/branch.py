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
    # [GIT SCOPING] Route git ops to workspace project if set, else agent_root
    root = state.get("project_root")

    # Create branch (the branch IS the snapshot — no separate snapshot needed)
    if state.get("branch"):
        _git_create_branch(state["branch"], tid, root)

    return {}
