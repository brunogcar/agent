"""
Git branch node.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_helpers.state import AutocodeState
from workflows.autocode_helpers.git_ops import _git_snapshot, _git_create_branch
from core.tracer import tracer

def node_git_branch(state: AutocodeState) -> dict:
    """Snapshot and create git branch before any code changes."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return {}
    # [GIT SCOPING] Route git ops to workspace project if set, else agent_root
    root = state.get("project_root")

    _git_snapshot(f"pre-autocode: {state['task'][:30]}", tid, root)
    if state.get("branch"):
        _git_create_branch(state["branch"], tid, root)

    return {}