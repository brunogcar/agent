"""
Debug node for autocode workflow.
"""

from __future__ import annotations

from typing import Any

from core.config import cfg
from core.memory import memory  # <-- Use your actual memory instance
from core.tracer import tracer
from workflows.autocode_helpers.helpers import _call
from workflows.autocode_helpers.state import AutocodeState

def node_systematic_debug(state: AutocodeState) -> AutocodeState:
    """
    Perform systematic debugging of test failures.
    """
    tid = state.get("trace_id", "")
    tracer.step(tid, "systematic_debug", "Starting systematic debug")

    max_retries = state.get("max_retries", cfg.autocode_max_retries)
    current_iteration = state.get("tdd_iteration", 0)

    if current_iteration > max_retries:
        error_msg = state.get("tdd_error", "Unknown TDD failure")
        tracer.error(tid, "systematic_debug", f"TDD exhausted after {max_retries} attempts: {error_msg}")

        # Store procedural memory using your actual memory API
        memory.store(
            text=f"TDD failed after {max_retries} iterations on task: '{state.get('task')}'. Error: {error_msg}",
            memory_type="procedural",  # Match your memory_pool.py API
            importance=9,
            tags="tdd_failure,retry_exhaustion,autocode",
            trace_id=tid,
            outcome="failed"
        )

        return {
            **state,
            "tdd_status": "max_retries_exceeded",
            "error": error_msg,
            "debug_notes": f"Debug abandoned after {max_retries} iterations. Last error: {error_msg}"
        }

    # Get test failure info
    test_results = state.get("test_results", {})
    stderr = test_results.get("stderr", "")
    stdout = test_results.get("stdout", "")

    # Generate debug analysis
    system = (
        "You are a senior debug engineer. Output ONLY valid JSON, no other text.\n"
        "Analyze the test failure and return a JSON object with these EXACT fields:\n"
        '{"root_cause": "string", "defense_notes": "string", "fix": "string"}'
    )
    user = f"Test failure:\n{stderr[:2000]}\n\nTest output:\n{stdout[:2000]}"

    try:
        debug_response = _call(
            role="executor",
            system=system,
            user=user,
            timeout=cfg.execution_timeout
        )
    except Exception as e:
        tracer.error(tid, "systematic_debug", f"Debug LLM call failed: {e}")
        return {**state, "status": "error", "error": f"Debug failed: {e}"}

    # Parse debug response (expecting JSON with root_cause, defense_notes, fix)
    import json, re
    try:
        clean_response = debug_response.strip()
        debug_data = json.loads(clean_response)
    except json.JSONDecodeError:
        match = re.search(r'\{[^{}]*\}', clean_response, re.DOTALL)
        debug_data = json.loads(match.group(0)) if match else {
            "root_cause": "Unknown",
            "defense_notes": "",
            "fix": ""
        }

    root_cause = debug_data.get("root_cause", "Unknown root cause")
    defense_notes = debug_data.get("defense_notes", "")
    suggested_fix = debug_data.get("fix", "")

    # Store debug info in state
    state["root_cause"] = root_cause
    state["defense_notes"] = defense_notes
    state["tdd_source_code"] = suggested_fix

    tracer.step(tid, "systematic_debug", f"Root cause: {root_cause[:100]}")
    return {**state, "debug_notes": f"Debug iteration {current_iteration}: {root_cause}"}