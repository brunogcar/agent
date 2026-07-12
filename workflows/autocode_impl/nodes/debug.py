"""
Debug node for autocode workflow.

[v1.3] Added optional swarm integration (AUTOCODE_SWARM_DEBUG=1):
  - Run 1: swarm(action="consensus") — all providers propose a fix
  - Run 2: swarm(action="vote") — providers vote on the consensus
  - Confidence: HIGH (unanimous) / MEDIUM (majority) / LOW (split/disagreement)
  - Non-blocking: fix always applies; LOW confidence → optional PR comment
  - Falls back to single-LLM debug if swarm unavailable or flag off

[v2.0] Phase 4 — 4-phase debug loop refactor (obra/superpowers systematic-debugging):
  - DEBUG_SYSTEM prompt restructured into investigation / pattern / hypothesis /
    fix. The LLM must declare its current phase in every JSON response.
  - debug_history accumulates per-iteration entries
    {iteration, phase, root_cause, fix[:200], tests_passed} so the LLM sees
    prior attempts and the orchestrator can detect stuck loops.
  - Architecture-question exit: if the last _ARCHITECTURE_QUESTION_THRESHOLD
    entries all have tests_passed=False, bail with tdd_status=
    "max_retries_exceeded" and store a procedural memory so the human can be
    asked an architecture question (the bug is likely architectural, not a
    fix-the-line bug).
  - summarize_context node (separate file) compresses debug_history before
    re-entering the loop — keeps context budget bounded (#37).
"""
from __future__ import annotations
import json, re
from typing import Any
from core.config import cfg
from core.memory_engine import memory
from core.tracer import tracer
from workflows.autocode_impl.constants import DEBUG_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json
from workflows.autocode_impl.state import AutocodeState, _get_tdd
from workflows.autocode_impl.vcs_ops import _swarm_debug_consensus, _github_pr_comment
from core.kgraph.queries import get_dependencies, get_callers

# [v2.0] Phase 4 — architecture-question threshold.
# If the last N debug_history entries all have tests_passed=False, the bug is
# likely architectural (not a fix-the-line bug). Bail and store a procedural
# memory so the human can be asked an architecture-level question.
_ARCHITECTURE_QUESTION_THRESHOLD = 3


def node_systematic_debug(state: AutocodeState) -> dict:
    tid = state.get("trace_id", "")
    tracer.step(tid, "systematic_debug", "Starting systematic debug")
    max_retries = state.get("max_retries", cfg.autocode_max_retries)
    current_iteration = state.get("tdd_iteration", 0)

    # [v2.0] Phase 4 — read accumulated debug history from sub-state (with
    # legacy flat fallback via _get_tdd accessor).
    debug_history = _get_tdd(state, "debug_history", []) or []

    # [v2.0] Phase 4 — architecture-question exit.
    # If the last N entries all have tests_passed=False, the bug is likely
    # architectural. Bail and store a procedural memory.
    if len(debug_history) >= _ARCHITECTURE_QUESTION_THRESHOLD:
        recent = debug_history[-_ARCHITECTURE_QUESTION_THRESHOLD:]
        if all(not entry.get("tests_passed", False) for entry in recent):
            error_msg = state.get("tdd_error", "Unknown TDD failure")
            tracer.error(
                tid, "systematic_debug",
                f"Architecture-question exit: last {_ARCHITECTURE_QUESTION_THRESHOLD} debug "
                f"iterations all failed tests — likely architecture-level issue."
            )
            memory.store(
                text=(
                    f"Debug loop bailed after {len(debug_history)} iterations on task: "
                    f"'{state.get('task')}'. Last {_ARCHITECTURE_QUESTION_THRESHOLD} attempts "
                    f"all failed tests — likely an architecture-level question, not a "
                    f"code-level bug. Last error: {error_msg}"
                ),
                memory_type="procedural",
                importance=9,
                tags="tdd_failure,architecture_question,autocode,phase4",
                trace_id=tid,
                outcome="failed"
            )
            # [Hardening] Read-modify-write: LangGraph replaces dict values, doesn't deep-merge.
            # Must preserve existing tdd sub-state fields.
            current_tdd = dict(state.get("tdd", {}))
            current_tdd["debug_history"] = debug_history
            current_tdd["status"] = "max_retries_exceeded"
            return {
                "tdd_status": "max_retries_exceeded",
                "error": error_msg,
                "debug_notes": (
                    f"Debug abandoned after {len(debug_history)} iterations — last "
                    f"{_ARCHITECTURE_QUESTION_THRESHOLD} all failed. Likely architecture-"
                    f"level issue: {error_msg}"
                ),
                "tdd": current_tdd,
            }

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

        # [Hardening] Read-modify-write to preserve tdd sub-state.
        current_tdd = dict(state.get("tdd", {}))
        current_tdd["debug_history"] = debug_history
        current_tdd["status"] = "max_retries_exceeded"
        return {
            "tdd_status": "max_retries_exceeded",
            "error": error_msg,
            "debug_notes": f"Debug abandoned after {max_retries} iterations. Last error: {error_msg}",
            "tdd": current_tdd,
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

    # [v2.0] Phase 4 — use DEBUG_SYSTEM from constants (4-phase structured prompt).
    # [Hardening P1.9] blast_radius_note was appended AFTER the "Output JSON ONLY:"
    # instruction, so the model saw the warning after the format spec (and might
    # interpret it as content). Insert BEFORE the format instruction so the
    # warning is part of the context, not the format spec.
    if blast_radius_note:
        format_idx = DEBUG_SYSTEM.find("Output JSON ONLY:")
        if format_idx > 0:
            system = DEBUG_SYSTEM[:format_idx] + blast_radius_note + "\n\n" + DEBUG_SYSTEM[format_idx:]
        else:
            system = DEBUG_SYSTEM + blast_radius_note
    else:
        system = DEBUG_SYSTEM

    # [v2.0] Phase 4 — include last 5 debug_history entries so the LLM sees
    # prior attempts and avoids repeating the same hypothesis/fix.
    history_block = ""
    if debug_history:
        recent_history = debug_history[-5:]
        lines = []
        for entry in recent_history:
            lines.append(
                f"- iteration {entry.get('iteration', '?')} "
                f"[phase={entry.get('phase', '?')}]: "
                f"{entry.get('root_cause', '?')[:120]} | "
                f"fix={entry.get('fix', '')[:120]}"
            )
        history_block = (
            "\n\n--- PRIOR DEBUG ATTEMPTS (do NOT repeat these) ---\n"
            + "\n".join(lines)
            + "\n--- END PRIOR ATTEMPTS ---\n"
        )

    # [Hardening P2] Wire debug_summary into the prompt: when the history is
    # long (>5 entries), node_summarize_context will have produced a compressed
    # debug_summary. Use that instead of the raw history block to keep the LLM
    # context bounded (#37) — the summary is what the orchestrator intends the
    # LLM to see in long-running debug loops.
    debug_summary = _get_tdd(state, "debug_summary", "")
    if debug_summary and len(debug_history) > 5:
        history_block = (
            "\n\n--- DEBUG SUMMARY (compressed) ---\n"
            f"{debug_summary}\n"
            "--- END SUMMARY ---\n"
        )

    user = (
        f"Test failure:\n{stderr[:2000]}\n\n"
        f"Test output:\n{stdout[:2000]}"
        f"{history_block}"
    )

    # [v1.3] Swarm debug integration (2-run pattern: consensus → vote)
    # Falls back to single-LLM debug if swarm is off, unavailable, or fails.
    # [v2.0] Phase 4 — swarm path now records a debug_history entry with
    # phase="swarm" and includes the swarm confidence.
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

            # [v2.0] Phase 4 — accumulate debug_history entry for swarm path.
            # phase="swarm" because the 4-phase enum is single-LLM only.
            new_entry = {
                "iteration": current_iteration,
                "phase": "swarm",
                "root_cause": root_cause,
                "fix": (suggested_fix or "")[:200],
                "tests_passed": False,  # updated by run_tests on next iteration
                "confidence": confidence,  # swarm-only field
            }
            updated_history = debug_history + [new_entry]

            # [Hardening] Read-modify-write to preserve tdd sub-state.
            current_tdd = dict(state.get("tdd", {}))
            current_tdd["debug_history"] = updated_history
            return {
                "root_cause": root_cause,
                "defense_notes": defense_notes,
                "tdd_source_code": suggested_fix,
                "debug_notes": f"Debug iteration {current_iteration} (swarm {confidence}): {root_cause}",
                "swarm_verdict": swarm_result,
                "tdd": current_tdd,
            }
        # Swarm failed — fall through to subagent or single-LLM debug
        tracer.step(tid, "systematic_debug", "Swarm unavailable — falling back")

    # [v1.1] Subagent debug — isolated curated-context LLM dispatch.
    # Uses agent(action="subagent") for a fresh LLM call with NO session history.
    # The subagent gets only the debug system prompt + test failure + history.
    # Different from single-LLM: no retry, no cancellation flag, isolated context.
    # Different from swarm: single LLM, not multi-provider consensus.
    if cfg.autocode_subagent_debug:
        from tools.agent import agent
        try:
            subagent_result = agent(
                action="subagent",
                role="executor",
                task=user,
                system=system,
                trace_id=tid,
            )
            if subagent_result.get("status") == "success":
                from core.json_extract import extract_json
                debug_data = extract_json(subagent_result.get("response", ""))
                if debug_data:
                    phase = debug_data.get("phase", "investigation")
                    root_cause = debug_data.get("root_cause", "Unknown")
                    defense_notes = debug_data.get("defense_notes", "")
                    suggested_fix = debug_data.get("fix", "")

                    tracer.step(tid, "systematic_debug", f"Subagent [phase={phase}] root cause: {root_cause[:100]}")

                    new_entry = {
                        "iteration": current_iteration,
                        "phase": phase,
                        "root_cause": root_cause,
                        "fix": (suggested_fix or "")[:200],
                        "tests_passed": False,
                    }
                    updated_history = debug_history + [new_entry]

                    current_tdd = dict(state.get("tdd", {}))
                    current_tdd["debug_history"] = updated_history
                    return {
                        "root_cause": root_cause,
                        "defense_notes": defense_notes,
                        "tdd_source_code": suggested_fix,
                        "debug_notes": f"Debug iteration {current_iteration} (subagent {phase}): {root_cause}",
                        "tdd": current_tdd,
                    }
            # Subagent failed — fall through to single-LLM
            tracer.step(tid, "systematic_debug", "Subagent unavailable — falling back to single-LLM debug")
        except Exception as e:
            tracer.step(tid, "systematic_debug", f"Subagent exception: {e} — falling back to single-LLM debug")

    # Single-LLM debug (default — used when AUTOCODE_SWARM_DEBUG=0 and
    # AUTOCODE_SUBAGENT_DEBUG=0, or when swarm/subagent are unavailable)
    # [v2.0] Phase 4 — JSON schema now includes `phase` field (enum of 4 phases).
    # LM Studio enforces this at generation time so the model cannot emit a
    # missing or invalid phase.
    _DEBUG_JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "enum": ["investigation", "pattern", "hypothesis", "fix"],
            },
            "root_cause": {"type": "string"},
            "defense_notes": {"type": "string"},
            "fix": {"type": "string"},
        },
        "required": ["phase", "root_cause", "defense_notes", "fix"],
        "additionalProperties": False,
    }

    try:
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
                "phase": "investigation",
                "root_cause": "Unknown",
                "defense_notes": "",
                "fix": ""
            }

    root_cause = debug_data.get("root_cause", "Unknown root cause")
    defense_notes = debug_data.get("defense_notes", "")
    suggested_fix = debug_data.get("fix", "")
    phase = debug_data.get("phase", "investigation")  # [v2.0] Phase 4

    # [v2.0] Phase 4 — validate phase against the allowed enum. If the LLM
    # returned an unknown value (shouldn't happen with schema enforcement,
    # but defensive), default to "investigation".
    if phase not in ("investigation", "pattern", "hypothesis", "fix"):
        tracer.warning(
            tid, "systematic_debug",
            f"Unknown phase '{phase}' from LLM — defaulting to 'investigation'"
        )
        phase = "investigation"

    tracer.step(tid, "systematic_debug", f"[phase={phase}] Root cause: {root_cause[:100]}")

    # [v2.0] Phase 4 — accumulate debug_history entry.
    # tests_passed=False here; updated to True by run_tests on the next loop
    # iteration (or by summarize_context if it inspects test_results).
    new_entry = {
        "iteration": current_iteration,
        "phase": phase,
        "root_cause": root_cause,
        "fix": (suggested_fix or "")[:200],
        "tests_passed": False,
    }
    updated_history = debug_history + [new_entry]

    # [Hardening] Read-modify-write to preserve tdd sub-state.
    current_tdd = dict(state.get("tdd", {}))
    current_tdd["debug_history"] = updated_history
    return {
        "root_cause": root_cause,
        "defense_notes": defense_notes,
        "tdd_source_code": suggested_fix,
        "debug_notes": f"Debug iteration {current_iteration} [phase={phase}]: {root_cause}",
        "tdd": current_tdd,
    }
