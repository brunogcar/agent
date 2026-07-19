"""[v3.1] Swarm fallback node — escalate to multi-model consensus when debug loop is exhausted.

When the debug loop hits max_retries_exceeded, instead of going straight to
the verify chain (which will fail), this node calls the swarm for a fresh
diagnosis from multiple LLMs. If swarm confidence is HIGH, the verdict is
injected into debug_history and tdd_status is reset to allow one more debug
cycle. If LOW or swarm unavailable, proceeds to the verify chain (which will
fail and surface the issue to the user).

This is the "escalation" pattern from loop-engineering: when a single agent
can't resolve an issue after N attempts, escalate to a multi-agent consensus
with a pruned context summary.

[v1.2] Removed unused `from workflows.autocode_impl.helpers import _call`
import (the node only calls `_swarm_debug_consensus` from vcs_ops — never
`_call` directly).
"""
from __future__ import annotations

from workflows.autocode_impl.state import AutocodeState, _get_tdd, _get_debug
from workflows.autocode_impl.vcs_ops import _swarm_debug_consensus
from workflows.autocode_impl.constants import DEBUG_SYSTEM
from core.config import cfg
from core.tracer import tracer


def node_swarm_fallback(state: AutocodeState) -> dict:
    """[v3.1 #48] Swarm fallback when debug retries are exhausted.

    Called when route_after_run_tests sees tdd_status == "max_retries_exceeded"
    AND AUTOCODE_SWARM_DEBUG_FALLBACK=1.

    Returns partial state update:
      - If swarm HIGH confidence: resets tdd_status to "" (allows one more
        debug cycle) + injects verdict into debug sub-state.
      - If LOW confidence or swarm unavailable: sets status="failed" (proceeds
        to verify chain which will fail and surface to user).
    """
    tid = state.get("trace_id", "")
    tracer.step(tid, "swarm_fallback", "Debug loop exhausted — escalating to swarm consensus")

    # Build the debug context for the swarm
    debug_history = _get_tdd(state, "debug_history", [])
    debug_summary = _get_tdd(state, "debug_summary", "")
    error = _get_tdd(state, "error", "Unknown error")

    # Use the compressed debug_summary if available (pruned context pattern),
    # otherwise build a summary from the last few debug_history entries.
    if debug_summary:
        context = f"Debug summary (compressed):\n{debug_summary[:2000]}\n\nLast error: {error}"
    elif debug_history:
        last_3 = debug_history[-3:]
        context = "Last 3 debug attempts:\n"
        for i, entry in enumerate(last_3):
            context += f"\n  Attempt {i+1}: root_cause={entry.get('root_cause', '?')[:200]}, fix={entry.get('fix', '?')[:200]}\n"
        context += f"\nLast error: {error}"
    else:
        context = f"No debug history available. Last error: {error}"

    # Call the swarm (2-run pattern: consensus → vote)
    swarm_result = _swarm_debug_consensus(
        system=DEBUG_SYSTEM,
        user=f"Debug loop exhausted after {cfg.autocode_max_retries} attempts. Multiple LLMs failed to fix this.\n\n{context}",
        tid=tid,
    )

    if swarm_result is None:
        # Swarm unavailable or failed — proceed to verify chain (will fail)
        tracer.step(tid, "swarm_fallback", "Swarm unavailable — proceeding to verify chain")
        return {"status": "failed"}

    confidence = swarm_result.get("confidence", "LOW")
    root_cause = swarm_result.get("root_cause", "Unknown")
    defense_notes = swarm_result.get("defense_notes", "")
    suggested_fix = swarm_result.get("fix", "")
    agreement = swarm_result.get("agreement", "unknown")
    providers = swarm_result.get("providers", 0)

    tracer.step(tid, "swarm_fallback", f"Swarm verdict: confidence={confidence}, agreement={agreement}, providers={providers}")

    if confidence == "HIGH":
        # High confidence — inject the verdict and allow one more debug cycle
        tracer.step(tid, "swarm_fallback", "HIGH confidence — injecting verdict, allowing one more debug cycle")

        # Write the swarm verdict to debug sub-state
        current_debug = dict(state.get("debug", {}))
        current_debug["root_cause"] = root_cause
        current_debug["defense_notes"] = defense_notes
        current_debug["swarm_verdict"] = swarm_result
        current_debug["notes"] = f"Swarm fallback (HIGH confidence): {root_cause[:200]}"

        # Reset tdd_status to allow one more debug cycle
        # Also set source_code to the suggested fix so debug node can use it
        current_tdd = dict(state.get("tdd", {}))
        current_tdd["status"] = ""  # reset — allows debug loop to retry
        # v1.4.2: Reset tdd_iteration so the debug node doesn't immediately bail.
        # tdd_iteration was at max_retries+1 (that's what triggered the fallback);
        # without this reset, debug.py would immediately bail on re-entry.
        current_tdd["iteration"] = 0  # reset — gives one full debug cycle
        current_tdd["source_code"] = suggested_fix
        current_tdd["error"] = error  # keep the error for context

        # [v1.4 P0] Append swarm verdict to debug_history so the debug LLM sees it.
        # Without this, the LLM repeats the same failed hypotheses the swarm already rejected.
        new_entry = {
            "iteration": 0,  # reset
            "phase": "swarm_fallback",
            "root_cause": root_cause,
            "fix": (suggested_fix or "")[:200],
            "tests_passed": False,
            "confidence": "HIGH",
        }
        current_tdd["debug_history"] = debug_history + [new_entry]

        # [v1.4 P0] Clear last_test_error so stuck detection doesn't short-circuit
        # the new debug cycle. The swarm's fix gets a clean retry.
        current_tdd["last_test_error"] = ""

        return {
            "tdd": current_tdd,
            "debug": current_debug,
        }
    else:
        # LOW/MEDIUM confidence — don't trust the swarm verdict, proceed to verify
        tracer.step(tid, "swarm_fallback", f"{confidence} confidence — proceeding to verify chain")

        # Still record the swarm verdict for the report
        current_debug = dict(state.get("debug", {}))
        current_debug["swarm_verdict"] = swarm_result
        current_debug["notes"] = f"Swarm fallback ({confidence} confidence): {root_cause[:200]}"

        return {
            "status": "failed",
            "debug": current_debug,
        }
