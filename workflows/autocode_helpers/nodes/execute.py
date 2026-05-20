"""
Execution node for autocode workflow.
"""

from __future__ import annotations

from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_helpers.helpers import _call, _write_files
from workflows.autocode_helpers.state import AutocodeState

def node_execute_step(state: AutocodeState) -> AutocodeState:
    """
    Execute the current step in the plan.
    """
    tid = state.get("trace_id", "")
    tracer.step(tid, "execute_step", "Executing plan step")

    # Get current plan step
    plan = state.get("plan", {})
    current_step = plan.get("steps", [{}])[state.get("step_index", 0)]

    if not current_step:
        return {**state, "status": "error", "error": "No plan step to execute"}

    # Use your actual config attributes
    system = """
    You are an expert Python developer. Generate clean, production-ready code.
    Return ONLY the code in a code block, no explanations.
    """
    user = f"Plan step: {current_step.get('description', '')}\nCurrent files:\n{state.get('files_context', '')}"

    try:
        code = _call(
            role="executor",
            system=system,
            user=user,
            timeout=cfg.execution_timeout  # Use your actual attribute name
        )
    except Exception as e:
        tracer.error(tid, "execute_step", f"LLM call failed: {e}")
        return {**state, "status": "error", "error": f"Execution failed: {e}"}

    if not code:
        return {**state, "status": "error", "error": "No code generated"}

    # Store generated code for TDD loop
    state["tdd_source_code"] = code

    # Write files if not dry run
    if not state.get("dry_run", False):
        write_result = _write_files(state)
        if write_result.get("error"):
            return {**state, "status": "error", "error": write_result["error"]}
        state["modified_files"] = write_result.get("files_written", [])

    tracer.step(tid, "execute_step", "Code generated and written")
    return {**state, "execution_notes": f"Executed step: {current_step.get('description', '')}"}