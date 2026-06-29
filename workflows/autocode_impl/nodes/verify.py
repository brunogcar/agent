"""Verification node."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from typing import Any

from workflows.autocode_impl.state import AutocodeState, EXECUTOR_TIMEOUT
from workflows.autocode_impl.constants import VERIFY_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json
from core.config import cfg
from core.tracer import tracer

def node_verify(state: AutocodeState) -> dict:
    """
    Verification gate. Runs fresh pytest + ruff. Real exit codes override LLM.
    Hallucination guard: if pytest failed but LLM claims pass, we trust pytest.
    """
    tid = state.get("trace_id", "")

    # Handle TDD max retries exceeded
    if state.get("tdd_status") == "max_retries_exceeded":
        tracer.error(tid, "verify", f"Verification skipped: TDD exhausted after {state.get('max_retries', cfg.autocode_max_retries)} attempts")
        try:
            from core.memory import memory
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
        # Return partial update without {**state, ...}
        return {
            "status": "failed",
            "verification_notes": "TDD max retries exceeded",
            "verification_passed": False,
            "trace_id": tid
        }

    if state.get("status") in ("needs_clarification", "failed"):
        return {}

    tracer.step(tid, "verify", "running automated checks")

    # Fresh pytest on autocode run directory
    tests_passed = False
    fresh_output = ""

    tid = state.get("trace_id", "")
    run_path = state.get("autocode_run_path", "")
    if run_path:
        run_dir = Path(run_path)
    else:
        from workflows.autocode_impl.helpers import _get_autocode_run_path
        run_dir = _get_autocode_run_path(tid)

    test_file = run_dir / "test_autocode_feature.py"
    tests_dir = run_dir / "tests"

    try:
        cmd = [sys.executable, "-m", "pytest", "--tb=short", "--color=no", "-q"]
        if tests_dir.exists():
            cmd.append(str(tests_dir))
        if test_file.exists():
            cmd.append(str(test_file))

        # Run from project root so imports resolve correctly
        base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding='utf-8', cwd=str(base_path))
        fresh_output = (result.stdout + result.stderr).strip()
        tests_passed = result.returncode == 0
    except FileNotFoundError:
        # [FIX 5] Specific handler for missing pytest
        fresh_output = "pytest not found in PATH — install with: pip install pytest"
        tests_passed = False
    except subprocess.TimeoutExpired as e:
        # [FIX 5] Specific handler for timeout
        fresh_output = f"pytest timed out after {e.timeout}s"
        tests_passed = False
    except Exception as e:
        fresh_output = f"pytest failed to run: {e}"

    # Ruff lint (non-fatal -- warnings don't block commit)
    lint_output = ""
    lint_passed = True
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(cfg.workspace_root),
             "--select", "E,F", "--no-cache"],
            capture_output=True, text=True, timeout=30, encoding='utf-8'
        )
        lint_output = (result.stdout + result.stderr).strip()
        lint_passed = result.returncode == 0
    except Exception as e:
        lint_output = f"ruff not available: {e}"
        lint_passed = True # non-fatal

    automated_ok = tests_passed # lint is advisory only

    tracer.step(tid, "verify",
        f"automated: {'PASS' if automated_ok else 'FAIL'} "
        f"(pytest={'OK' if tests_passed else 'FAIL'}, "
        f"lint={'OK' if lint_passed else 'WARN'}) ")

    # LLM review (for spec coverage and cleanliness) - WITH ERROR HANDLING
    # [FIX] tdd_source_code is JSON patches/new_files, not raw Python.
    # Build a clean implementation context from the actual generated artifacts.
    impl_ctx = ""
    try:
        code_data = json.loads(state.get("tdd_source_code", "{}"))
        parts = []
        for patch in code_data.get("patches", []):
            parts.append(f"# Patch: {patch.get('path', '')}\n```python\n{patch.get('new', '')[:1500]}\n```")
        for path, content in code_data.get("new_files", {}).items():
            parts.append(f"# New file: {path}\n```python\n{str(content)[:1500]}\n```")
        impl_ctx = "\n\n".join(parts) if parts else state.get("tdd_source_code", "")[:3000]
    except Exception:
        impl_ctx = state.get("tdd_source_code", "")[:3000]

    try:
        raw = _call(
            role = "executor",
            system = VERIFY_SYSTEM,
            user = (
                f"Spec:\n{state.get('spec', '')}\n\n"
                f"Implementation:\n```python\n{impl_ctx[:3000]}\n```\n\n"
                f"Tests:\n```python\n{state.get('test_code', '')[:1000]}\n```\n\n"
                f"FRESH PYTEST OUTPUT (exit code {'0' if tests_passed else '1'}):\n"
                f"{fresh_output[:2000]}\n\n"
                f"RUFF OUTPUT:\n{lint_output[:500]}"
            ),
            timeout = EXECUTOR_TIMEOUT,
        )
        data = _parse_json(raw) if raw else {}
    except Exception as e:
        tracer.error(tid, "verify", f"LLM verification failed: {e}")
        data = {"automated_checks_passed": False, "checks": {}, "summary": "LLM verification error"}

    # Hallucination guard: real exit code overrides LLM claim
    llm_claims_tests_ok = data.get("automated_checks_passed", True)
    if not tests_passed and llm_claims_tests_ok:
        tracer.step(tid, "verify", "HALLUCINATION DETECTED: LLM claimed tests passed but pytest failed")

    llm_checks_ok = all(
        data.get("checks", {}).get(k, {}).get("passed", False)
        for k in ("syntax", "tests", "spec", "regressions", "cleanliness")
    )

    # Final decision: automated_ok (real) AND llm_checks_ok (spec/cleanliness)
    all_passed = automated_ok and llm_checks_ok
    summary = data.get("summary", "verification incomplete")
    notes = json.dumps(data.get("checks", {}), indent=2) if data else "No LLM checks available"

    tracer.step(tid, "verify", f"result: {'PASS' if all_passed else 'FAIL'} -- {summary[:80]}")
    # Return partial update without {**state, ...}
    return {
        "verification_passed": all_passed,
        "verification_notes": (
            f"Automated: {'PASS' if automated_ok else 'FAIL'} | "
            f"LLM: {'PASS' if llm_checks_ok else 'FAIL'}\n"
            f"{summary}\n\n{notes}"
        ),
        "evidence_outputs": {
            "tests": fresh_output[:2000],
            "lint": lint_output[:500],
            "regression": fresh_output[:2000],
        },
        "trace_id": tid
    }
