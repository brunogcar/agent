"""
Execution node for autocode workflow.
"""

from __future__ import annotations

import json
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.constants import CODER_SYSTEM
from workflows.autocode_impl.helpers import _call, _files_context, _parse_json  # [v2.0] removed dead _write_files import
from workflows.autocode_impl.state import AutocodeState

def node_execute_step(state: AutocodeState) -> dict:
    """
    Execute the current step in the plan.
    """
    tid = state.get("trace_id", "")
    tracer.step(tid, "execute_step", "Executing plan step")
    # [FIX] Schema drift: plan is a list[dict], not a dict with "steps" key
    plan = state.get("plan", [])
    current_step_idx = state.get("current_step", 0)
    if current_step_idx >= len(plan):
        return {"status": "error", "error": "No more plan steps"}
    current_step = plan[current_step_idx]

    if not current_step:
        return {"status": "error", "error": "No plan step to execute"}

    # Use your actual config attributes
    system = CODER_SYSTEM
    user = f"Plan step: {current_step.get('description', '')}\nCurrent files:\n{_files_context(state.get('files', {}))}"
    try:
        code = _call(
            role="executor",
            system=system,
            user=user,
            timeout=cfg.execution_timeout  # Use your actual attribute name
        )
    except Exception as e:
        tracer.error(tid, "execute_step", f"LLM call failed: {e}")
        return {"status": "error", "error": f"Execution failed: {e}"}

    if not code:
        return {"status": "error", "error": "No code generated"}

    # Store generated code for TDD loop
    updates = {"tdd_source_code": code}

    # Derive modified_files from generated code JSON (only when not dry_run)
    # [Pre-2.0 Fix] Was: raw json.loads(code) — fails on markdown-fenced output.
    # Now uses _parse_json which strips ```json fences before parsing.
    # [Hardening P2] Removed dead `json.loads(code)` fallback — _parse_json already
    # tries direct json.loads as its first strategy (see core.json_extract.extract_json).
    # The fallback was unreachable when _parse_json returned {}, and would raise
    # JSONDecodeError (caught by the except) on truly invalid JSON.
    if not state.get("dry_run", False):
        try:
            code_data = _parse_json(code)
            if not code_data:
                tracer.warning(tid, "execute_step", "Failed to parse LLM output as JSON — modified_files empty")
                updates["modified_files"] = []
            else:
                modified = []
                for patch in code_data.get("patches", []):
                    modified.append(patch.get("path", ""))
                modified.extend(code_data.get("new_files", {}).keys())
                updates["modified_files"] = [m for m in modified if m]
        except Exception:
            updates["modified_files"] = []

    tracer.step(tid, "execute_step", "Code generated and written")
    updates["execution_notes"] = f"Executed step: {current_step.get('description', '')}"
    updates["current_step"] = current_step_idx + 1
    return updates