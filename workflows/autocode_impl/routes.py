"""
Routing functions for the autocode state machine.
"""
from __future__ import annotations
from workflows.autocode_impl.state import AutocodeState, _get_tdd, _get_verify
from core.config import cfg  # [v3.1 #48] for autocode_swarm_debug_fallback flag

def route_after_classify(state: AutocodeState) -> str:
    """Route after task classification node.

    [v3.7 F7] audit now bypasses the TDD pipeline entirely — routes to
    node_audit_scan, which scans the whole repo and produces a read-only
    report. No tests written, no code modified, no commit.
    """
    task_type = state.get("task_type", "unclear")
    if task_type == "unclear":
        return "END"
    elif task_type == "create_skill":
        return "node_create_skill"
    elif task_type == "audit":
        return "node_audit_scan"  # [v3.7 F7] audit bypasses TDD
    else:
        return "node_validate_input"

def route_after_write_files(state: AutocodeState) -> str:
    """Route after writing files node.

    [v1.1] Added 'audit' and 'edit' to the impact-analysis path. Previously
    these fell through to node_verify, skipping impact analysis entirely —
    which is wrong for 'audit' (an audit IS impact analysis) and inconsistent
    for 'edit' (the docs say edit is 'heavier than fix' but it skipped TDD).
    Found by cross-LLM review (DeepSeek, Mistral).

    [Hardening P1.5] If a prior node set status="error" (e.g. apply_patches
    JSON parse failure), skip impact analysis and go straight to the verify
    chain — run_pytest will fail and the verify_decision node will route to END.

    [Hardening P2] Removed dead 'fix_error' and 'improve' entries — classify.py
    normalizes both (fix_error -> fix, improve -> refactor), so they can never
    reach this router.
    """
    # [Hardening P1.5] Short-circuit on prior node error.
    if state.get("status") == "error":
        return "node_verify"  # routes to run_pytest (first verify sub-node)
    task_type = state.get("task_type", "feature")
    if task_type in ["fix", "refactor", "feature", "audit", "edit"]:
        return "node_analyze_impact"
    else:
        return "node_verify"

# [Pre-2.0 Fix] DELETED: route_after_analyze_impact — was always constant
# ("node_run_tests"), replaced with direct edge in graph.py.
# Found by: mimo P3.16.

def route_after_run_tests(state: AutocodeState) -> str:
    """Route after running tests node.

    [#39] 'stuck' status (same error signature on consecutive iterations) now
    routes to node_verify — skips the doomed debug loop. The debug node would
    just regenerate the same fix for the same error.

    [Hardening P1.5] If a prior node set status="error" (e.g. apply_patches
    JSON parse failure), skip the debug loop and go to verify_chain which
    handles errors via verify_decision.

    [v3.1 #48] When tdd_status == "max_retries_exceeded" AND
    AUTOCODE_SWARM_DEBUG_FALLBACK=1, route to node_swarm_fallback instead of
    node_verify. The swarm fallback may inject a fresh diagnosis and allow
    one more debug cycle (HIGH confidence), or proceed to verify (LOW).
    """
    # [Hardening P1.5] Short-circuit on prior node error.
    if state.get("status") == "error":
        return "node_verify"  # routes to run_pytest (first verify sub-node)
    tdd_status = _get_tdd(state, "status", "")  # [v3.0] accessor (was flat field)
    test_results = state.get("test_results", {})  # [v3.0] stays flat (ephemeral)
    if tdd_status == "passed" or test_results.get("success"):
        return "node_verify"
    elif tdd_status == "max_retries_exceeded":
        # [v3.1 #48] Swarm fallback — escalate to multi-model consensus
        if getattr(cfg, "autocode_swarm_debug_fallback", False):
            return "node_swarm_fallback"
        return "node_verify"
    elif tdd_status == "stuck":
        # [#39] Bail to verify — the debug loop is spinning on the same error.
        return "node_verify"
    else:
        return "node_systematic_debug"

def route_after_verify(state: AutocodeState) -> str:
    """Route after verification node."""
    if _get_verify(state, "passed", False):  # [v3.0] accessor (was flat field)
        return "report"
    else:
        return "END"


def route_after_swarm_fallback(state: AutocodeState) -> str:
    """[v1.4 P2] Route after swarm fallback node.

    HIGH confidence → node_systematic_debug (one more debug cycle with the
    swarm's verdict injected into debug_history).
    LOW/unavailable → node_verify (verify chain, will fail and surface to user).

    Replaces the inline lambda that was previously in graph.py — extracted so
    it can be tested directly and documented alongside the other routers.
    """
    if _get_tdd(state, "status", "") == "" and state.get("status") != "failed":
        return "node_systematic_debug"
    return "node_verify"


def route_after_hitl_gate(state: AutocodeState) -> str:
    """[v3.4 #38] Route after HiTL gate.

    [v3.11.1 B2-fix] Allow-list approach — only "running"/"success"/no-status
    proceed to node_commit. Everything else (awaiting_approval,
    hitl_checkpoint_failed, failed, error, or any future new status) routes to
    END. This fails safe: a checkpoint-save failure (v3.11 B2) or any
    unrecognized status can NEVER silently fall through to commit. Pre-v3.11.1,
    the router only checked `status == "awaiting_approval"` → the new
    `hitl_checkpoint_failed` status fell through to `node_commit`, bypassing
    HiTL entirely on a plain disk/IO hiccup — strictly worse than the original
    bug B2 was meant to fix.
    """
    # [v3.11.1 B2-fix] Allow-list: only explicit approval/proceed statuses
    # route to commit. This is safer than block-listing (awaiting_approval +
    # hitl_checkpoint_failed) because any FUTURE new status added to
    # node_hitl_gate fails safe → END instead of silently committing.
    if state.get("status") in ("running", "success", "", None):
        return "node_commit"
    # awaiting_approval, hitl_checkpoint_failed, failed, error, or any
    # unrecognized status → END (fail safe).
    return "END"
