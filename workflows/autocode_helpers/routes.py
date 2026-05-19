"""
Routing functions for the autocode state machine.
"""

from __future__ import annotations
from typing import Any
from workflows.autocode_helpers.state import AutocodeState

def route_after_classify(state: AutocodeState) -> str:
    """Route after task classification node."""
    classification = state.get("classification", {})
    task_type = classification.get("task_type", state.get("task_type", "unclear"))

    if task_type == "unclear":
        return "END"
    elif task_type == "create_skill":
        return "node_create_skill"
    else:
        return "node_brainstorm"

def route_after_brainstorm(state: AutocodeState) -> str:
    """Route after brainstorming node."""
    if state.get("status") == "needs_clarification":
        return "END"
    return "node_write_plan"

def route_after_run_tests(state: AutocodeState) -> str:
    """Route after running tests node."""
    test_result = state.get("test_result", "")
    if "passed" in test_result.lower() or state.get("test_result") == "":
        return "node_verify"
    else:
        return "node_systematic_debug"

def route_after_debug(state: AutocodeState) -> str:
    """Route after debugging node."""
    return "node_run_tests"

def route_after_write_files(state: AutocodeState) -> str:
    """Route after writing files node."""
    task_type = state.get("task_type", "feature")
    if task_type in ["fix", "fix_error", "refactor", "improve"]:
        return "node_run_tests"
    else:
        return "node_verify"

def route_after_verify(state: AutocodeState) -> str:
    """Route after verification node."""
    if state.get("verification_passed", False):
        return "node_commit"
    else:
        return "END"