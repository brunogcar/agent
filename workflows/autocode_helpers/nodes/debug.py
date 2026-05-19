"""
Systematic debugging node.
"""

from __future__ import annotations

import json
from typing import Any

from workflows.autocode_helpers.state import AutocodeState, EXECUTOR_TIMEOUT, MAX_RETRIES
from workflows.autocode_helpers.constants import DEBUG_SYSTEM
from workflows.autocode_helpers.helpers import _call, _parse_json, _files_context
from core.tracer import tracer

def node_systematic_debug(state: AutocodeState) -> AutocodeState:
    """Hypothesis-driven debugging. One targeted fix per attempt."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state
    if not state.get("error_log"):
        return state

    attempts = state.get("debug_attempts", 0)
    if attempts >= MAX_RETRIES:
        tracer.step(tid, "debug", f"exhausted after {attempts} attempts")
        return {**state, "status": "failed",
                "result": f"Max retries ({MAX_RETRIES}) reached.\n{state['error_log']}"}

    tracer.step(tid, "debug", f"attempt {attempts + 1}")

    try:
        gen_files = json.loads(state["generated_code"])
        impl_ctx  = "\n\n".join(f"# {p}\n{c}" for p, c in gen_files.items())
    except Exception:
        impl_ctx = state.get("generated_code", "")

    raw  = _call(
        role    = "executor",
        system  = DEBUG_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"Tests:\n```python\n{state['test_code']}\n```\n\n"
            f"Implementation:\n```python\n{impl_ctx}\n```\n\n"
            f"Error:\n```\n{state['error_log']}\n```\n\n"
            f"Existing files:\n{_files_context(state['files'])}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    data = _parse_json(raw)

    hypothesis   = data.get("hypothesis", "unknown")
    fixed_files  = data.get("files", {})
    defense_note = data.get("defense_note", "")
    generated    = json.dumps(fixed_files, indent=2)

    tracer.step(tid, "debug", f"hypothesis: {hypothesis[:80]}")
    return {**state,
            "hypothesis":     hypothesis,
            "defense_note":   defense_note,
            "generated_code": generated,
            "debug_attempts": attempts + 1,
            "came_from_debug": True,
            "error_log":      ""}