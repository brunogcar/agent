"""
Routing functions for the autocode state machine.
"""
from __future__ import annotations
from typing import Any
from workflows.autocode_impl.state import AutocodeState

def route_after_classify(state: AutocodeState) -> str:
    """Route after task classification node."""
    task_type = state.get("task_type", "unclear")
    if task_type == "unclear":
        return "END"
    elif task_type == "create_skill":
        return "node_create_skill"
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
    """
    # [Hardening P1.5] Short-circuit on prior node error.
    if state.get("status") == "error":
        return "node_verify"  # routes to run_pytest (first verify sub-node)
    tdd_status = state.get("tdd_status", "")
    test_results = state.get("test_results", {})
    if tdd_status == "passed" or test_results.get("success"):
        return "node_verify"
    elif tdd_status == "max_retries_exceeded":
        return "node_verify"
    elif tdd_status == "stuck":
        # [#39] Bail to verify — the debug loop is spinning on the same error.
        return "node_verify"
    else:
        return "node_systematic_debug"

def route_after_verify(state: AutocodeState) -> str:
    """Route after verification node."""
    if state.get("verification_passed", False):
        return "report"
    else:
        return "END"
