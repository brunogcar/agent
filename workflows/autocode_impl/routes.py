"""
Routing functions for the autocode state machine.
"""
from __future__ import annotations
from typing import Any
from workflows.autocode_impl.state import AutocodeState

def route_after_classify(state: AutocodeState) -> str:
    """Route after task classification node."""
    task_type = state.get("task_type", "unclear")
    if task_type == "unclear":
        return "END"
    elif task_type == "create_skill":
        return "node_create_skill"
    else:
        return "node_validate_input"

def route_after_brainstorm(state: AutocodeState) -> str:
    """Route after brainstorming node."""
    if state.get("status") == "needs_clarification":
        return "END"
    return "node_write_plan"

def route_after_write_files(state: AutocodeState) -> str:
    """Route after writing files node."""
    task_type = state.get("task_type", "feature")
    if task_type in ["fix", "fix_error", "refactor", "improve", "feature"]:
        # CHANGED: Route to analyze_impact first
        return "node_analyze_impact"
    else:
        return "node_verify"

def route_after_analyze_impact(state: AutocodeState) -> str:
    """Route after impact analysis node. Always proceeds to run_tests."""
    return "node_run_tests"

def route_after_run_tests(state: AutocodeState) -> str:
    """Route after running tests node."""
    tdd_status = state.get("tdd_status", "")
    test_results = state.get("test_results", {})
    if tdd_status == "passed" or test_results.get("success"):
        return "node_verify"
    elif tdd_status == "max_retries_exceeded":
        return "node_verify"
    else:
        return "node_systematic_debug"

def route_after_debug(state: AutocodeState) -> str:
    """Route after debugging node."""
    if state.get("tdd_status") == "max_retries_exceeded":
        return "node_verify"  # Fail gracefully and exit the TDD loop
    return "node_run_tests"

def route_after_verify(state: AutocodeState) -> str:
    """Route after verification node."""
    if state.get("verification_passed", False):
        return "report"
    else:
        return "END"
