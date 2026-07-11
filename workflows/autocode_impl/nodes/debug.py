"""
Debug node for autocode workflow.

[v1.3] Added optional swarm integration (AUTOCODE_SWARM_DEBUG=1):
  - Run 1: swarm(action="consensus") — all providers propose a fix
  - Run 2: swarm(action="vote") — providers vote on the consensus
  - Confidence: HIGH (unanimous) / MEDIUM (majority) / LOW (split/disagreement)
  - Non-blocking: fix always applies; LOW confidence → optional PR comment
  - Falls back to single-LLM debug if swarm unavailable or flag off

# TODO(2.0): The debug node is stateless per iteration (each call sees only
# current test output, no accumulated history). This blocks context
# summarization (#37). Should be refactored in 2.0 to accumulate debug_notes
# across iterations for the swarm consensus prompt.
"""
from __future__ import annotations
import json, re
from typing import Any
from core.config import cfg
from core.memory_engine import memory
from core.tracer import tracer
from workflows.autocode_impl.helpers import _call, _parse_json
from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.github_ops import _swarm_debug_consensus, _github_pr_comment
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

    # [v1.3] Swarm debug integration (2-run pattern: consensus → vote)
    # Falls back to single-LLM debug if swarm is off, unavailable, or fails.
    # TODO(2.0): Consider making swarm the default debug path for cloud-enabled setups.
    if cfg.autocode_swarm_debug:
        swarm_result = _swarm_debug_consensus(system, user, tid)
        if swarm_result is not None:
            root_cause = swarm_result.get("root_cause", "Unknown")
            defense_notes = swarm_result.get("defense_notes", "")
            suggested_fix = swarm_result.get("fix", "")
            confidence = swarm_result.get("confidence", "LOW")
            agreement = swarm_result.get("agreement", "unknown")
            providers = swarm_result.get("providers", 0)

            tracer.step(tid, "systematic_debug", f"Swarm root cause: {root_cause[:100]} (confidence={confidence})")

            # If LOW confidence + PR exists + flag enabled → post PR comment
            # so human reviewers can see the disagreement
            # TODO(2.0): Also post for MEDIUM confidence if providers < 3
            if (confidence == "LOW" and cfg.autocode_debug_comment_pr
                    and state.get("pr_number")):
                comment = (
                    f"⚠️ **Low-confidence swarm debug verdict**\n\n"
                    f"**Root cause:** {root_cause[:500]}\n"
                    f"**Agreement:** {agreement} ({providers} providers)\n\n"
                    f"Fix was applied automatically, but please review carefully."
                )
                _github_pr_comment(state["pr_number"], comment, tid)

            return {
                "root_cause": root_cause,
                "defense_notes": defense_notes,
                "tdd_source_code": suggested_fix,
                "debug_notes": f"Debug iteration {current_iteration} (swarm {confidence}): {root_cause}",
                "swarm_verdict": swarm_result,
            }
        # Swarm failed — fall through to single-LLM debug
        tracer.step(tid, "systematic_debug", "Swarm unavailable — falling back to single-LLM debug")

    # Single-LLM debug (existing v1.2 behavior — used when AUTOCODE_SWARM_DEBUG=0
    # or when swarm is unavailable)
    try:
        # Autocode v1.2: JSON schema enforcement — LM Studio enforces the debug
        # schema at generation time. The model cannot produce root_cause/
        # defense_notes/fix with wrong types or missing fields.
        _DEBUG_JSON_SCHEMA = {
            "type": "object",
            "properties": {
                "root_cause": {"type": "string"},
                "defense_notes": {"type": "string"},
                "fix": {"type": "string"},
            },
            "required": ["root_cause", "defense_notes", "fix"],
            "additionalProperties": False,
        }
        debug_response = _call(
            role="executor",
            system=system,
            user=user,
            timeout=cfg.execution_timeout,
            temperature=retry_temp,
            json_schema=_DEBUG_JSON_SCHEMA,
        )
    except Exception as e:
        tracer.error(tid, "systematic_debug", f"Debug LLM call failed: {e}")
        return {"status": "error", "error": f"Debug failed: {e}"}

    try:
        clean_response = debug_response.strip()
        debug_data = json.loads(clean_response)
    except json.JSONDecodeError:
        debug_data = _parse_json(clean_response)
        if not debug_data:
            debug_data = {
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