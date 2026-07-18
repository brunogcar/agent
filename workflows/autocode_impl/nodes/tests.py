"""
Test writing node.
"""

from __future__ import annotations

from workflows.autocode_impl.state import AutocodeState, EXECUTOR_TIMEOUT, _get_plan  # [v3.0] _get_files removed (files is core flat)
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
            f"Existing files:\n{_files_context(state.get('files', {}))}\n\n"  # [v3.0] files is core flat field
            f"Step: {step['description']}"
        ),
        timeout = EXECUTOR_TIMEOUT,
        trace_id=tid,  # [v1.2 P1] attribute retry-exhaustion errors to this trace
    )
    test_code = _extract_code(raw)
    tracer.step(tid, "write_tests", f"tests written ({len(test_code)} chars)")

    # [v2.2] RMW: write to plan sub-state for current_step (sub-state only in v3.0)
    current_plan = dict(state.get("plan_state", {}))
    current_plan["current_step"] = idx + 1
    return {"test_code": test_code, "plan_state": current_plan}
