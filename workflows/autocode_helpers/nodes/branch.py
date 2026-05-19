"""
Git branch node.
"""

from __future__ import annotations
from typing import Any
from workflows.autocode_helpers.state import AutocodeState
from workflows.autocode_helpers.git_ops import _git_snapshot, _git_create_branch
from core.tracer import tracer

def node_git_branch(state: AutocodeState) -> AutocodeState:
    """Snapshot and create git branch before any code changes."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    _git_snapshot(f"pre-autocode: {state['task'][:30]}", tid)
    if state.get("branch"):
        _git_create_branch(state["branch"], tid)

    return state