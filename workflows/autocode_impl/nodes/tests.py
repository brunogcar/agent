"""
Test writing node.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_impl.state import AutocodeState, EXECUTOR_TIMEOUT, _get_plan, _get_files  # [v2.2+v2.3] accessors
from workflows.autocode_impl.constants import TEST_SYSTEM
from workflows.autocode_impl.helpers import _call, _extract_code, _files_context
from core.tracer import tracer

def node_write_tests(state: AutocodeState) -> dict:
    """TDD red phase -- write failing tests before implementation."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return {}
    plan = _get_plan(state, "plan", [])  # [v2.2] accessor
    if not isinstance(plan, list):  # [SAFETY] Prevent KeyError if plan was overwritten
        plan = []
    idx = _get_plan(state, "current_step", 0)  # [v2.2] accessor
    if idx >= len(plan) or plan[idx].get("label") != "write_tests":
        return {}

    step = plan[idx]
    tracer.step(tid, "write_tests", f"step {step['id']}")

    raw       = _call(
        role    = "executor",
        system  = TEST_SYSTEM,
        user    = (
            f"Spec:\n{_get_plan(state, 'spec', '')}\n\n"  # [v2.2] accessor
            f"Existing files:\n{_files_context(_get_files(state, 'input_files', {}))}\n\n"  # [v2.3] accessor
            f"Step: {step['description']}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    test_code = _extract_code(raw)
    tracer.step(tid, "write_tests", f"tests written ({len(test_code)} chars)")

    # [v2.2] RMW: write to plan sub-state + flat mirror for current_step
    current_plan = dict(state.get("plan_state", {}))
    current_plan["current_step"] = idx + 1
    return {"test_code": test_code, "current_step": idx + 1, "plan_state": current_plan}