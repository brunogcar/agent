"""Test runner node for autocode workflow."""

from __future__ import annotations

import subprocess
import sys

from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.state import AutocodeState

def run_tests_on_disk(test_files: list[str], project_root: str = None, targeted_cmd: str | None = None) -> dict:
    """
    Run pytest on the given test files, or use a targeted command string.
    """
    if project_root is None:
        project_root = str(cfg.workspace_root)

    if targeted_cmd:
        # targeted_cmd is like "pytest tests/test_a.py tests/test_b.py"
        parts = targeted_cmd.split()
        if parts and parts[0] == "pytest":
            cmd = [sys.executable, "-m", "pytest"] + parts[1:]
        else:
            cmd = parts
    else:
        test_paths = []
        for tf in test_files:
            if tf.startswith("autocode/"):
                test_paths.append(str(cfg.workspace_root / tf))
            else:
                test_paths.append(str(Path(project_root) / tf))
        cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", *test_paths]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.sandbox_timeout,
            cwd=project_root # Run in the project root directory
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Tests timed out after {cfg.sandbox_timeout}s",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -2
        }

def node_run_tests(state: AutocodeState) -> dict:
    """
    Run tests for the current TDD iteration.
    """
    tid = state.get("trace_id", "")
    tracer.step(tid, "run_tests", "Running tests")
    # Get test files from state
    test_files = state.get("test_files", [])
    if not test_files:
        return {"status": "error", "error": "No test files to run"}

    # [P2 #14] Filter out test files that don't exist on disk —
    # write_files may have failed to write them, causing pytest to crash.
    from pathlib import Path as _Path
    from core.config import cfg as _cfg
    existing_test_files = []
    for tf in test_files:
        base = _Path(state.get("project_root", "")) if state.get("project_root") else _cfg.workspace_root
        full_path = base / tf
        if full_path.exists():
            existing_test_files.append(tf)
        else:
            tracer.step(tid, "run_tests", f"test file missing, skipping: {tf}")
    if not existing_test_files:
        return {"status": "error", "error": "All test files missing from disk"}

    # Run tests with existing files only
    project_root = state.get("project_root", None)
    targeted_cmd = state.get("targeted_test_cmd", None)
    test_results = run_tests_on_disk(existing_test_files, project_root=project_root, targeted_cmd=targeted_cmd)
    current_iter = state.get("tdd_iteration", 0) + 1

    # Build partial update dict instead of mutating state directly
    updates = {
        "test_results": test_results,
        "tdd_iteration": current_iter,
    }

    if test_results.get("success"):
        tracer.step(tid, "run_tests", f"Tests passed in {current_iter} iterations")
        updates["tdd_status"] = "passed"
        updates["tdd_error"] = ""
        updates["last_test_error"] = ""  # [#39] clear on success

        # [PHASE 3 FIX] Wire success callback: store procedural memory on convergence
        try:
            from core.memory_engine import memory
            memory.store(
                text=f"TDD converged after {current_iter} iterations for task: '{state.get('task', '')}'",
                memory_type="procedural",
                importance=7,
                tags="tdd_success,converged,autocode",
                trace_id=tid,
                outcome="success"
            )
        except Exception:
            pass # Non-fatal: memory storage failure should not break the workflow

    else:
        current_error = test_results.get("stderr", "Tests failed")
        updates["tdd_error"] = current_error
        # [#39] Stuck detection: compare error signature to previous iteration.
        # If the same error repeats and we're past iteration 1, the debug loop
        # is spinning on the same mistake — bail to verify instead of looping.
        prev_error = state.get("last_test_error", "")
        if prev_error and current_iter > 1 and _error_signature(prev_error) == _error_signature(current_error):
            tracer.warning(
                tid, "run_tests",
                f"Stuck detection: same error signature on iteration {current_iter}, bailing to verify"
            )
            updates["tdd_status"] = "stuck"
        else:
            updates["tdd_status"] = "failed"
        updates["last_test_error"] = current_error
        tracer.step(tid, "run_tests", f"Tests failed (iteration {current_iter}, status={updates['tdd_status']})")

    return updates


def _error_signature(error_text: str) -> str:
    """[#39] Extract a comparable error signature from test stderr.

    Normalizes the error so trivial differences (file paths, line numbers,
    tracebacks) don't mask a stuck loop. We keep the last few lines that
    usually contain the actual assertion/error type.
    """
    if not error_text:
        return ""
    lines = [ln.strip() for ln in error_text.splitlines() if ln.strip()]
    # Take the last 3 non-empty lines — usually the assertion + error type.
    # This ignores path/line-number noise at the top of tracebacks.
    return "\n".join(lines[-3:]) if lines else ""
