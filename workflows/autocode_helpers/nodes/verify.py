"""
Verification node.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from workflows.autocode_helpers.state import AutocodeState, EXECUTOR_TIMEOUT
from workflows.autocode_helpers.constants import VERIFY_SYSTEM
from workflows.autocode_helpers.helpers import _call, _parse_json
from core.config import cfg
from core.tracer import tracer

def node_verify(state: AutocodeState) -> AutocodeState:
    """
    Verification gate. Runs fresh pytest + ruff. Real exit codes override LLM.
    Hallucination guard: if pytest failed but LLM claims pass, we trust pytest.
    """
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return state

    tracer.step(tid, "verify", "running automated checks")

    # -- Fresh pytest on agent root --
    tests_passed  = False
    fresh_output  = ""
    test_file     = cfg.agent_root / "autocode" / "test_autocode_feature.py"
    tests_dir     = cfg.agent_root / "tests"

    try:
        cmd = [sys.executable, "-m", "pytest", "--tb=short", "--color=no", "-q"]
        if tests_dir.exists():
            cmd.append(str(tests_dir))
        if test_file.exists():
            cmd.append(str(test_file))

        result       = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        fresh_output = (result.stdout + result.stderr).strip()
        tests_passed = result.returncode == 0
    except Exception as e:
        fresh_output = f"pytest failed to run: {e}"

    # -- Ruff lint (non-fatal -- warnings don't block commit) --
    lint_output = ""
    lint_passed = True
    try:
        result      = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(cfg.agent_root),
             "--select", "E,F", "--no-cache"],
            capture_output=True, text=True, timeout=30,
        )
        lint_output = (result.stdout + result.stderr).strip()
        lint_passed = result.returncode == 0
    except Exception as e:
        lint_output = f"ruff not available: {e}"
        lint_passed = True  # non-fatal

    automated_ok = tests_passed  # lint is advisory only

    tracer.step(tid, "verify",
                f"automated: {'PASS' if automated_ok else 'FAIL'} "
                f"(pytest={'OK' if tests_passed else 'FAIL'}, "
                f"lint={'OK' if lint_passed else 'WARN'})")

    # -- LLM review (for spec coverage and cleanliness) --
    try:
        gen_files = json.loads(state["generated_code"])
        impl_ctx  = "\n\n".join(f"# {p}\n{c}" for p, c in gen_files.items())
    except Exception:
        impl_ctx = state.get("generated_code", "")

    raw  = _call(
        role    = "executor",
        system  = VERIFY_SYSTEM,
        user    = (
            f"Spec:\n{state['spec']}\n\n"
            f"Implementation:\n```python\n{impl_ctx[:3000]}\n```\n\n"
            f"Tests:\n```python\n{state['test_code'][:1000]}\n```\n\n"
            f"FRESH PYTEST OUTPUT (exit code {'0' if tests_passed else '1'}):\n"
            f"{fresh_output[:2000]}\n\n"
            f"RUFF OUTPUT:\n{lint_output[:500]}"
        ),
        timeout = EXECUTOR_TIMEOUT,
    )
    data = _parse_json(raw)

    # Hallucination guard: real exit code overrides LLM claim
    llm_claims_tests_ok = data.get("automated_checks_passed", True)
    if not tests_passed and llm_claims_tests_ok:
        tracer.step(tid, "verify",
                    "HALLUCINATION DETECTED: LLM claimed tests passed but pytest failed")

    llm_checks_ok = all(
        data.get("checks", {}).get(k, {}).get("passed", False)
        for k in ("syntax", "tests", "spec", "regressions", "cleanliness")
    )

    # Final decision: automated_ok (real) AND llm_checks_ok (spec/cleanliness)
    all_passed = automated_ok and llm_checks_ok
    summary    = data.get("summary", "verification incomplete")
    notes      = json.dumps(data.get("checks", {}), indent=2)

    tracer.step(tid, "verify", f"result: {'PASS' if all_passed else 'FAIL'} -- {summary[:80]}")
    return {**state,
            "verification_passed": all_passed,
            "verification_notes":  (
                f"Automated: {'PASS' if automated_ok else 'FAIL'} | "
                f"LLM: {'PASS' if llm_checks_ok else 'FAIL'}\n"
                f"{summary}\n\n{notes}"
            ),
            "evidence_outputs": {
                "tests":      fresh_output[:2000],
                "lint":       lint_output[:500],
                "regression": fresh_output[:2000],
            }}