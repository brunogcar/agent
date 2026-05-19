"""
Test writing node.
"""

from __future__ import annotations
from typing import Any
from workflows.autocode_helpers.state import AutocodeState, EXECUTOR_TIMEOUT
from workflows.autocode_helpers.constants import TEST_SYSTEM
from workflows.autocode_helpers.helpers import _call, _extract_code, _files_context
from core.tracer import tracer

def node_write_tests(state: AutocodeState) -> AutocodeState:
    """TDD red phase -- write failing tests before implementation."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    plan = state.get("plan", [])
    idx  = state.get("current_step", 0)
    if idx >= len(plan) or plan[idx]["label"] != "write_tests":
        return state

    step = plan[idx]
    tracer.step(tid, "write_tests", f"step {step['id']}")

    raw       = _call(
        role    = "executor",
        system  = TEST_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"Existing files:\n{_files_context(state['files'])}\n\n"
            f"Step: {step['description']}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    test_code = _extract_code(raw)
    tracer.step(tid, "write_tests", f"tests written ({len(test_code)} chars)")

    return {**state, "test_code": test_code, "current_step": idx + 1}