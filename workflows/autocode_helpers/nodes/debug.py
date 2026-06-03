"""
Debug node for autocode workflow.
"""
from __future__ import annotations
import json, re
from typing import Any
from core.config import cfg
from core.memory import memory
from core.tracer import tracer
from workflows.autocode_helpers.helpers import _call
from workflows.autocode_helpers.state import AutocodeState
from core.kgraph.queries import get_dependencies, get_callers

def node_systematic_debug(state: AutocodeState) -> dict:
    tid = state.get("trace_id", "")
    tracer.step(tid, "systematic_debug", "Starting systematic debug")
    max_retries = state.get("max_retries", cfg.autocode_max_retries)
    current_iteration = state.get("tdd_iteration", 0)
    
    if current_iteration > max_retries:
        error_msg = state.get("tdd_error", "Unknown TDD failure")
        tracer.error(tid, "systematic_debug", f"TDD exhausted after {max_retries} attempts: {error_msg}")

        memory.store(
            text=f"TDD failed after {max_retries} iterations on task: '{state.get('task')}'. Error: {error_msg}",
            memory_type="procedural",
            importance=9,
            tags="tdd_failure,retry_exhaustion,autocode",
            trace_id=tid,
            outcome="failed"
        )

        return {
            "tdd_status": "max_retries_exceeded",
            "error": error_msg,
            "debug_notes": f"Debug abandoned after {max_retries} iterations. Last error: {error_msg}"
        }

    test_results = state.get("test_results", {})
    stderr = test_results.get("stderr", "")
    stdout = test_results.get("stdout", "")

    base_temp = 0.1
    jitter = current_iteration * 0.15
    retry_temp = min(base_temp + jitter, 0.8)

    # --- Phase 6: Blast Radius Context Injection ---
    blast_radius_note = ""
    project_root = state.get("project_root", "")
    modified_files = state.get("modified_files", [])

    if project_root and modified_files:
        try:
            from core.config import cfg
            from pathlib import Path
            is_agent = (str(Path(project_root).resolve()) == str(cfg.agent_root.resolve()))
            from core.kgraph.project import ProjectManager
            pm = ProjectManager(project_root, is_agent_root=is_agent)
            
            callers = []
            for f in modified_files[:3]:
                deps = get_callers(pm.path, f)
                callers.extend([c for c in deps if c not in modified_files])
            
            if callers:
                unique_callers = list(set(callers))[:5]
                blast_radius_note = f"\n\n⚠️ BLAST RADIUS WARNING: The files you are modifying are also used by: {', '.join(unique_callers)}. Ensure your fix does not break these callers."
        except Exception:
            pass

    system = (
        "You are a senior debug engineer. Output ONLY valid JSON, no other text.\n"
        "Analyze the raw test failure below. Ignore any previous assumptions or "
        "speculative reasoning from prior attempts. Base your diagnosis STRICTLY "
        "on the provided traceback and test output." + blast_radius_note + "\n"
        'Return a JSON object with these EXACT fields:\n'
        '{ "root_cause": "string", "defense_notes": "string", "fix": "string"}'
    )
    user = f"Test failure:\n{stderr[:2000]}\n\nTest output:\n{stdout[:2000]}"

    try:
        debug_response = _call(
            role="executor",
            system=system,
            user=user,
            timeout=cfg.execution_timeout,
            temperature=retry_temp
        )
    except Exception as e:
        tracer.error(tid, "systematic_debug", f"Debug LLM call failed: {e}")
        return {"status": "error", "error": f"Debug failed: {e}"}

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

    tracer.step(tid, "systematic_debug", f"Root cause: {root_cause[:100]}")
    return {
        "root_cause": root_cause,
        "defense_notes": defense_notes,
        "tdd_source_code": suggested_fix,
        "debug_notes": f"Debug iteration {current_iteration}: {root_cause}"
    }