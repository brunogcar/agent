"""
Step execution node.
"""

from __future__ import annotations

import json
from typing import Any

from workflows.autocode_helpers.state import AutocodeState, EXECUTOR_TIMEOUT
from workflows.autocode_helpers.constants import CODER_SYSTEM
from workflows.autocode_helpers.helpers import _call, _parse_json, _files_context
from core.config import cfg
from core.tracer import tracer

def node_execute_step(state: AutocodeState) -> AutocodeState:
    """Generate code for the current plan step."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    plan = state.get("plan", [])
    idx  = state.get("current_step", 0)
    if idx >= len(plan):
        return state

    step = plan[idx]
    if step["label"] in ("write_tests", "verify"):
        return state

    attempt = state.get("step_attempt", 0) + 1
    tracer.step(tid, "execute_step", f"step {step['id']} ({step['label']}) attempt {attempt}")

    test_ctx = (
        f"Tests to satisfy:\n```python\n{state['test_code']}\n```\n\n"
        if state.get("test_code") else ""
    )

    raw  = _call(
        role    = "executor",
        system  = CODER_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"{test_ctx}"
            f"Current step ({step['id']}): {step['description']}\n"
            f"Acceptance: {step['acceptance']}\n\n"
            f"Existing files:\n{_files_context(state['files'], hint=state.get('task',''))}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    data = _parse_json(raw)
    # Support both old format (files dict) and new patch format
    if "patches" in data or "new_files" in data:
        generated = json.dumps(data, indent=2)
    else:
        generated = json.dumps({"new_files": data.get("files", {})}, indent=2)

    tracer.step(tid, "execute_step", f"code generated ({len(generated)} chars)")
    return {**state, "generated_code": generated, "step_attempt": attempt}