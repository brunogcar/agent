"""[v2.0] Verify decision node — composes results + hallucination guard.

Split from node_verify (Phase 3.2). This node reads the results from the
3 previous nodes (run_pytest, run_lint, llm_review) and makes the final
verification decision. Also handles the max_retries_exceeded/stuck early exit.
"""
from __future__ import annotations

import json

from workflows.autocode_impl.state import AutocodeState
from core.config import cfg
from core.tracer import tracer


def node_verify_decision(state: AutocodeState) -> dict:
    """[v2.0] Compose verification results + hallucination guard.

    Returns partial state update with:
      - verification_passed: bool
      - verification_notes: str (summary for downstream nodes)
      - evidence_outputs: dict (test/lint/regression outputs)
      - status: "failed" if max_retries/stuck
    """
    tid = state.get("trace_id", "")

    # Handle TDD max retries exceeded OR stuck (early exit)
    tdd_status = state.get("tdd_status", "")
    if tdd_status in ("max_retries_exceeded", "stuck"):
        reason = "TDD exhausted" if tdd_status == "max_retries_exceeded" else "TDD stuck (same error repeated)"
        tracer.error(tid, "verify_decision", f"Verification skipped: {reason} after {state.get('max_retries', cfg.autocode_max_retries)} attempts")
        try:
            from core.memory_engine import memory
            memory.store(
                text=f"Verification skipped due to TDD exhaustion on task: '{state.get('task', 'Unknown')}'. Error: {state.get('tdd_error', 'Unknown')}",
                memory_type="procedural",
                importance=8,
                tags="tdd_failure,verify_skipped,autocode",
                trace_id=tid,
                outcome="failed"
            )
        except Exception:
            pass
        # [v2.6] RMW: write to verify sub-state + flat mirrors
        current_verify = dict(state.get("verify", {}))
        current_verify["passed"] = False
        current_verify["notes"] = f"TDD {tdd_status}"
        return {
            "status": "failed",
            "verification_notes": current_verify["notes"],
            "verification_passed": False,
            "verify": current_verify,
            "trace_id": tid,
        }

    if state.get("status") in ("needs_clarification", "failed"):
        return {}

    # Read results from previous nodes
    tests_passed = state.get("tests_passed", False)
    lint_passed = state.get("lint_passed", None)
    fresh_output = state.get("_pytest_output", state.get("test_results", {}).get("stderr", ""))
    lint_output = state.get("lint_output", "")
    data = state.get("llm_review_data", {})

    automated_ok = tests_passed  # lint is advisory only

    tracer.step(tid, "verify_decision",
        f"automated: {'PASS' if automated_ok else 'FAIL'} "
        f"(pytest={'OK' if tests_passed else 'FAIL'}, "
        f"lint={'OK' if lint_passed else 'WARN'})")

    # Hallucination guard: real exit code overrides LLM claim
    llm_claims_tests_ok = data.get("automated_checks_passed", True)
    if not tests_passed and llm_claims_tests_ok:
        tracer.step(tid, "verify_decision", "HALLUCINATION DETECTED: LLM claimed tests passed but pytest failed")

    llm_checks_ok = all(
        data.get("checks", {}).get(k, {}).get("passed", False)
        for k in ("syntax", "tests", "spec", "regressions", "cleanliness")
    )

    # Final decision: automated_ok (real) AND llm_checks_ok (spec/cleanliness)
    all_passed = automated_ok and llm_checks_ok
    summary = data.get("summary", "verification incomplete")
    notes = json.dumps(data.get("checks", {}), indent=2) if data else "No LLM checks available"

    tracer.step(tid, "verify_decision", f"result: {'PASS' if all_passed else 'FAIL'} -- {summary[:80]}")

    # [v2.6] RMW: write to verify sub-state + flat mirrors
    current_verify = dict(state.get("verify", {}))
    current_verify["passed"] = all_passed
    current_verify["notes"] = (
        f"Automated: {'PASS' if automated_ok else 'FAIL'} | "
        f"LLM: {'PASS' if llm_checks_ok else 'FAIL'}\n"
        f"{summary}\n\n{notes}"
    )
    return {
        "verification_passed": all_passed,
        "verification_notes": current_verify["notes"],
        "evidence_outputs": {
            "tests": fresh_output[:2000],
            "lint": lint_output[:500],
            "regression": fresh_output[:2000],
        },
        "verify": current_verify,
        "trace_id": tid,
    }
