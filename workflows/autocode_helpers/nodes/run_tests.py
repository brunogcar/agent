"""
Test runner node for autocode workflow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_helpers.state import AutocodeState

def run_tests_on_disk(test_files: list[str], project_root: str = None) -> dict:
    """
    Run pytest on the given test files in a subprocess.
    """
    # Use workspace_root as default, but allow override
    if project_root is None:
        project_root = str(cfg.workspace_root)
    
    test_paths = [str(Path(project_root) / tf) for tf in test_files]
    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", *test_paths]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.sandbox_timeout,
            cwd=project_root  # Run in the project root directory
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

def node_run_tests(state: AutocodeState) -> AutocodeState:
    """
    Run tests for the current TDD iteration.
    """
    tid = state.get("trace_id", "")
    tracer.step(tid, "run_tests", "Running tests")

    # Get test files from state
    test_files = state.get("test_files", [])
    if not test_files:
        return {**state, "status": "error", "error": "No test files to run"}

    # Run tests
    test_results = run_tests_on_disk(test_files)
    state["test_results"] = test_results

    # Update TDD iteration
    state["tdd_iteration"] = state.get("tdd_iteration", 0) + 1

    if test_results.get("success"):
        tracer.step(tid, "run_tests", f"Tests passed in {state['tdd_iteration']} iterations")
        state["tdd_status"] = "passed"
        state["tdd_error"] = ""
    else:
        state["tdd_status"] = "failed"
        state["tdd_error"] = test_results.get("stderr", "Tests failed")
        tracer.step(tid, "run_tests", f"Tests failed (iteration {state['tdd_iteration']})")

    return state