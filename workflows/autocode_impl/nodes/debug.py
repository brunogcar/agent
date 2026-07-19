"""
Debug node for autocode workflow.

[v1.3] Added optional swarm integration (AUTOCODE_SWARM_DEBUG=1):
  - Run 1: swarm(action="consensus") — all providers propose a fix
  - Run 2: swarm(action="vote") — providers vote on the consensus
  - Confidence: HIGH (unanimous) / MEDIUM (majority) / LOW (split/disagreement)
  - Non-blocking: fix always applies; LOW confidence → optional PR comment
  - Falls back to single-LLM debug if swarm unavailable or flag off

[v3.5 F1] Parallel subagent debug (AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1):
  - 4th debug path, inserted between swarm and single-subagent in the chain.
  - Generates N distinct hypotheses via a planner LLM call
    (PARALLEL_HYPOTHESES_SYSTEM), dispatches N subagents in parallel via
    ThreadPoolExecutor (one per hypothesis, SUBAGENT_VALIDATE_SYSTEM),
    aggregates by picking the highest-confidence verdict. All verdicts
    stored in debug.parallel_verdicts for observability.
  - Mutually exclusive with AUTOCODE_SWARM_DEBUG and AUTOCODE_SUBAGENT_DEBUG
    (INSTRUCTIONS.md NEVER DO #40).
  - Falls through to single-LLM on hypothesis-generation failure or all-
    subagents-failed.

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

[v1.2] Removed unused imports (re, Any, get_dependencies) — get_callers is
the only kgraph query used here.
"""
from __future__ import annotations
import concurrent.futures  # [v3.5 F1] parallel subagent dispatch
import json
from core.config import cfg
from core.memory_engine import memory
from core.tracer import tracer
from workflows.autocode_impl.constants import (
    DEBUG_SYSTEM,
    PARALLEL_HYPOTHESES_SYSTEM,  # [v3.5 F1]
    SUBAGENT_VALIDATE_SYSTEM,    # [v3.5 F1]
)
from workflows.autocode_impl.helpers import _call, _parse_json, _blast_radius_warning  # [v1.4 P2] _blast_radius_warning extracted
from workflows.autocode_impl.state import AutocodeState, _get_tdd, _get_vcs, _get_files  # [v2.1+v2.3] accessors
from workflows.autocode_impl.vcs_ops import _swarm_debug_consensus, _github_pr_comment

# [v2.0] Phase 4 — architecture-question threshold.
# If the last N debug_history entries all have tests_passed=False, the bug is
# likely architectural (not a fix-the-line bug). Bail and store a procedural
# memory so the human can be asked an architecture-level question.
# [v3.3 F4] Configurable via AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD env var (default 3)
_ARCHITECTURE_QUESTION_THRESHOLD = cfg.autocode_architecture_question_threshold

# [v2.0.4] Shared JSON schema for the debug LLM response. Used by both the
# single-LLM debug path (default) and the subagent debug path
# (AUTOCODE_SUBAGENT_DEBUG=1). Was duplicated inline in both paths — deduped
# to module level so there's one source of truth for the 4-phase enum.
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


def _parallel_subagent_debug(
    system: str,
    user: str,
    tid: str,
    retry_temp: float,
    debug_history: list[dict],
    current_iteration: int,
    state: dict,
) -> dict | None:
    """[v3.5 F1] Parallel subagent debug — N hypotheses, N subagents, aggregate.

    Pipeline:
      1. Call the planner LLM with ``PARALLEL_HYPOTHESES_SYSTEM`` (templated with
         ``cfg.autocode_parallel_subagent_count``) to emit N distinct hypotheses
         as a JSON array.
      2. Parse the JSON array. If parsing fails OR fewer than 2 hypotheses are
         returned, return ``None`` so the caller falls through to single-LLM.
      3. Dispatch N subagents in parallel via
         ``concurrent.futures.ThreadPoolExecutor(max_workers=N)`` — one per
         hypothesis. Each subagent gets ``SUBAGENT_VALIDATE_SYSTEM`` + the
         hypothesis + the original debug context (test failure + history) and
         is asked to validate/refine it.
      4. Aggregate: pick the verdict with the highest ``hypothesis_confidence``
         (the planner-supplied confidence). Store ALL verdicts in
         ``debug.parallel_verdicts`` for observability.
      5. Build the same return shape as the existing single-subagent path so
         the rest of ``node_systematic_debug`` doesn't change.

    Returns:
        Partial state update dict (same shape as the single-subagent path) —
        or ``None`` to signal "fall through to single-subagent / single-LLM".
    """
    from core.json_extract import extract_json, extract_json_array
    from tools.agent import agent

    n = cfg.autocode_parallel_subagent_count
    if n < 2:
        # < 2 hypotheses makes parallel dispatch pointless — fall through.
        tracer.step(
            tid, "systematic_debug",
            f"parallel subagent count={n} < 2 — falling back to single-LLM",
        )
        return None

    # 1. Generate hypotheses via a planner LLM call.
    hypotheses_system = PARALLEL_HYPOTHESES_SYSTEM.format(count=n)
    try:
        hypotheses_response = _call(
            role="planner",
            system=hypotheses_system,
            user=user,
            timeout=cfg.execution_timeout,
            temperature=retry_temp,
            trace_id=tid,
        )
    except Exception as e:
        tracer.step(
            tid, "systematic_debug",
            f"Parallel hypothesis generation failed: {e} — falling back to single-LLM",
        )
        return None

    # 2. Parse JSON array of hypotheses.
    try:
        hypotheses = extract_json_array(hypotheses_response)
    except Exception:
        hypotheses = []
    if not isinstance(hypotheses, list) or len(hypotheses) < 2:
        got = len(hypotheses) if isinstance(hypotheses, list) else 0
        tracer.step(
            tid, "systematic_debug",
            f"Parallel hypothesis generation returned {got} hypotheses "
            f"(need >= 2) — falling back to single-LLM",
        )
        return None

    # Cap to the configured count (LLM may return extra or fewer).
    hypotheses = hypotheses[:n]
    tracer.step(
        tid, "systematic_debug",
        f"Parallel subagent debug: dispatching {len(hypotheses)} subagents "
        f"(confidence-weighted aggregation)",
    )

    # 3. Dispatch N subagents in parallel — one per hypothesis.
    # Each subagent gets: the hypothesis it must validate + the original debug
    # context (test failure + history) so it can reason about whether the
    # hypothesis explains the failure.
    def _dispatch(hypothesis: dict) -> dict | None:
        hid = hypothesis.get("hypothesis_id", "?")
        h_root_cause = hypothesis.get("root_cause", "?")
        h_proposed_fix = hypothesis.get("proposed_fix", "")
        try:
            h_confidence = float(hypothesis.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            h_confidence = 0.0
        subagent_task = (
            f"Hypothesis #{hid} (confidence={h_confidence:.2f}):\n"
            f"  root_cause: {h_root_cause}\n"
            f"  proposed_fix: {h_proposed_fix}\n\n"
            f"--- DEBUG CONTEXT ---\n{user}\n--- END CONTEXT ---\n\n"
            f"Validate this hypothesis. If it explains the test failure, "
            f"refine the fix. If not, propose an alternative root_cause + fix."
        )
        try:
            result = agent(
                action="subagent",
                role="executor",
                task=subagent_task,
                system=SUBAGENT_VALIDATE_SYSTEM,
                trace_id=tid,
                temperature=retry_temp,
                json_schema=json.dumps(_DEBUG_JSON_SCHEMA),
            )
            if result.get("status") != "success":
                return None
            debug_data = extract_json(result.get("response", ""))
            if not debug_data:
                tracer.warning(
                    tid, "systematic_debug",
                    f"Parallel subagent #{hid} returned unparseable response: "
                    f"{result.get('response', '')[:200]}",
                )
                return None
            return {
                "hypothesis_id": hid,
                "hypothesis_root_cause": h_root_cause,
                "hypothesis_confidence": h_confidence,
                "phase": debug_data.get("phase", "investigation"),
                "root_cause": debug_data.get("root_cause", "Unknown"),
                "defense_notes": debug_data.get("defense_notes", ""),
                "fix": debug_data.get("fix", ""),
            }
        except Exception as e:
            tracer.warning(
                tid, "systematic_debug",
                f"Parallel subagent #{hid} exception: {e}",
            )
            return None

    verdicts: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hypotheses)) as pool:
        future_map = {pool.submit(_dispatch, h): h for h in hypotheses}
        for future in concurrent.futures.as_completed(future_map):
            v = future.result()
            if v is not None:
                verdicts.append(v)

    # 4. Aggregate — pick highest hypothesis_confidence. If no verdicts
    # survived, fall through.
    if not verdicts:
        tracer.step(
            tid, "systematic_debug",
            "All parallel subagents failed — falling back to single-LLM debug",
        )
        return None

    verdicts.sort(
        key=lambda v: v.get("hypothesis_confidence", 0.0),
        reverse=True,
    )
    best = verdicts[0]
    tracer.step(
        tid, "systematic_debug",
        f"Parallel subagent aggregation: {len(verdicts)}/{len(hypotheses)} "
        f"succeeded — winner hypothesis #{best.get('hypothesis_id', '?')} "
        f"(confidence={best.get('hypothesis_confidence', 0.0):.2f})",
    )

    # 5. Build the same return shape as the single-subagent path so the rest
    # of node_systematic_debug doesn't change.
    phase = best.get("phase", "investigation")
    if phase not in ("investigation", "pattern", "hypothesis", "fix"):
        phase = "investigation"
    root_cause = best.get("root_cause", "Unknown")
    defense_notes = best.get("defense_notes", "")
    suggested_fix = best.get("fix", "")

    new_entry = {
        "iteration": current_iteration,
        "phase": phase,
        "root_cause": root_cause,
        "fix": (suggested_fix or "")[:200],
        "tests_passed": False,
    }
    updated_history = debug_history + [new_entry]

    # [Hardening] Read-modify-write to preserve sibling sub-state fields.
    current_tdd = dict(state.get("tdd", {}))
    current_tdd["debug_history"] = updated_history
    current_tdd["source_code"] = suggested_fix
    current_debug = dict(state.get("debug", {}))
    current_debug["root_cause"] = root_cause
    current_debug["defense_notes"] = defense_notes
    current_debug["notes"] = (
        f"Debug iteration {current_iteration} (parallel subagent {phase}, "
        f"{len(verdicts)}/{len(hypotheses)} hypotheses): {root_cause}"
    )
    current_debug["parallel_verdicts"] = verdicts  # ALL verdicts for observability
    # Mirror the winning verdict into subagent_verdict so downstream readers
    # that already look at subagent_verdict see the parallel winner too.
    current_debug["subagent_verdict"] = {
        "fix": suggested_fix,
        "root_cause": root_cause,
        "defense_notes": defense_notes,
    }
    return {
        "tdd": current_tdd,
        "debug": current_debug,
    }


def node_systematic_debug(state: AutocodeState) -> dict:
    tid = state.get("trace_id", "")
    tracer.step(tid, "systematic_debug", "Starting systematic debug")
    max_retries = _get_tdd(state, "max_retries", cfg.autocode_max_retries)  # [v3.0] accessor
    current_iteration = _get_tdd(state, "iteration", 0)  # [v3.0] accessor

    # [v2.0] Phase 4 — read accumulated debug history from tdd sub-state.
    debug_history = _get_tdd(state, "debug_history", []) or []

    # [v2.0] Phase 4 — architecture-question exit.
    # If the last N entries all have tests_passed=False, the bug is likely
    # architectural. Bail and store a procedural memory.
    if len(debug_history) >= _ARCHITECTURE_QUESTION_THRESHOLD:
        recent = debug_history[-_ARCHITECTURE_QUESTION_THRESHOLD:]
        if all(not entry.get("tests_passed", False) for entry in recent):
            error_msg = _get_tdd(state, "error", "Unknown TDD failure")  # [v3.0] accessor
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
            # [v2.5] RMW: write to debug sub-state
            current_debug = dict(state.get("debug", {}))
            current_debug["notes"] = (
                f"Debug abandoned after {len(debug_history)} iterations — last "
                f"{_ARCHITECTURE_QUESTION_THRESHOLD} all failed. Likely architecture-"
                f"level issue: {error_msg}"
            )
            return {
                "error": error_msg,
                "tdd": current_tdd,
                "debug": current_debug,
            }

    if current_iteration > max_retries:
        error_msg = _get_tdd(state, "error", "Unknown TDD failure")  # [v3.0] accessor
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
        # [v2.5] RMW: write to debug sub-state
        current_debug = dict(state.get("debug", {}))
        current_debug["notes"] = f"Debug abandoned after {max_retries} iterations. Last error: {error_msg}"
        return {
            "error": error_msg,
            "tdd": current_tdd,
            "debug": current_debug,
        }

    test_results = state.get("test_results", {})
    stderr = test_results.get("stderr", "")
    stdout = test_results.get("stdout", "")

    base_temp = 0.1
    jitter = current_iteration * 0.15
    retry_temp = min(base_temp + jitter, 0.8)

    # --- Phase 6: Blast Radius Context Injection ---
    # [v1.4 P2] Inline block extracted to helpers._blast_radius_warning().
    project_root = state.get("project_root", "")
    modified_files = _get_files(state, "modified_files", [])  # [v2.3] accessor
    blast_radius_note = _blast_radius_warning(project_root, modified_files, tid)

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
                    and _get_vcs(state, "pr_number", 0)):  # [v2.1] accessor
                comment = (
                    f"⚠️ **Low-confidence swarm debug verdict**\n\n"
                    f"**Root cause:** {root_cause[:500]}\n"
                    f"**Agreement:** {agreement} ({providers} providers)\n\n"
                    f"Fix was applied automatically, but please review carefully."
                )
                _github_pr_comment(_get_vcs(state, "pr_number", 0), comment, tid)  # [v2.1] accessor

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
            current_tdd["source_code"] = suggested_fix  # [v3.0] sub-state write (was flat tdd_source_code)
            # [v2.5] RMW: write to debug sub-state
            current_debug = dict(state.get("debug", {}))
            current_debug["root_cause"] = root_cause
            current_debug["defense_notes"] = defense_notes
            current_debug["notes"] = f"Debug iteration {current_iteration} (swarm {confidence}): {root_cause}"
            current_debug["swarm_verdict"] = swarm_result
            return {
                "tdd": current_tdd,
                "debug": current_debug,
            }
        # Swarm failed — fall through to subagent or single-LLM debug
        tracer.step(tid, "systematic_debug", "Swarm unavailable — falling back")

    # [v3.5 F1] Parallel subagent debug — N hypotheses, N subagents, aggregate.
    # Generates N distinct hypotheses via a planner LLM call, dispatches N
    # subagents in parallel via ThreadPoolExecutor (one per hypothesis),
    # aggregates by picking the highest-confidence verdict. Falls through to
    # single-subagent / single-LLM on hypothesis-generation failure or all-
    # subagents-failed. Mutually exclusive with swarm + single-subagent flags
    # (INSTRUCTIONS.md NEVER DO #40).
    if cfg.autocode_parallel_subagent_debug:
        result = _parallel_subagent_debug(
            system, user, tid, retry_temp, debug_history, current_iteration, state
        )
        if result:
            return result
        # Fall through to single-subagent / single-LLM if parallel failed
        tracer.step(
            tid, "systematic_debug",
            "Parallel subagent debug yielded no usable result — falling back to single-LLM",
        )

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
                temperature=retry_temp,  # [Hardening] pass retry temperature
                json_schema=json.dumps(_DEBUG_JSON_SCHEMA),  # [v2.0.4] module-level schema (was inline dup)
            )
            if subagent_result.get("status") == "success":
                from core.json_extract import extract_json
                debug_data = extract_json(subagent_result.get("response", ""))
                if not debug_data:
                    # [Hardening] Log when subagent returns unparseable response
                    tracer.warning(tid, "systematic_debug",
                        f"Subagent returned unparseable response: {subagent_result.get('response', '')[:200]}")
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
                    current_tdd["source_code"] = suggested_fix  # [v3.0] sub-state write (was flat tdd_source_code)
                    # [v2.5] RMW: write to debug sub-state
                    current_debug = dict(state.get("debug", {}))
                    current_debug["root_cause"] = root_cause
                    current_debug["defense_notes"] = defense_notes
                    current_debug["notes"] = f"Debug iteration {current_iteration} (subagent {phase}): {root_cause}"
                    current_debug["subagent_verdict"] = {
                        "fix": suggested_fix,
                        "root_cause": root_cause,
                        "defense_notes": defense_notes,
                    }
                    return {
                        "tdd": current_tdd,
                        "debug": current_debug,
                    }
            # Subagent failed or returned unparseable JSON — fall through to single-LLM
            tracer.step(tid, "systematic_debug", "Subagent debug path yielded no usable result — falling back to single-LLM debug")
        except Exception as e:
            tracer.step(tid, "systematic_debug", f"Subagent exception: {e} — falling back to single-LLM debug")

    # Single-LLM debug (default — used when AUTOCODE_SWARM_DEBUG=0 and
    # AUTOCODE_SUBAGENT_DEBUG=0, or when swarm/subagent are unavailable)
    # [v2.0] Phase 4 — JSON schema includes `phase` field (enum of 4 phases).
    # LM Studio enforces this at generation time so the model cannot emit a
    # missing or invalid phase. Schema is module-level (_DEBUG_JSON_SCHEMA) —
    # shared with the subagent debug path (v2.0.4 dedup).

    try:
        debug_response = _call(
            role="executor",
            system=system,
            user=user,
            timeout=cfg.execution_timeout,
            temperature=retry_temp,
            json_schema=_DEBUG_JSON_SCHEMA,
            trace_id=tid,  # [v1.2 P1] attribute retry-exhaustion errors to this trace
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
    current_tdd["source_code"] = suggested_fix  # [v3.0] sub-state write (was flat tdd_source_code)
    # [v2.5] RMW: write to debug sub-state
    current_debug = dict(state.get("debug", {}))
    current_debug["root_cause"] = root_cause
    current_debug["defense_notes"] = defense_notes
    current_debug["notes"] = f"Debug iteration {current_iteration} [phase={phase}]: {root_cause}"
    return {
        "tdd": current_tdd,
        "debug": current_debug,
    }
