"""[v2.0] Run pytest node — fresh pytest subprocess on autocode run directory.

Split from node_verify (Phase 3.2). This node runs pytest on the test files
in the per-run autocode folder. Lint, LLM review, and final decision are
handled by separate nodes:
  - node_run_lint (next)
  - node_llm_review (after lint)
  - node_verify_decision (composes all results)
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from workflows.autocode_impl.state import AutocodeState
from core.config import cfg
from core.tracer import tracer


def node_run_pytest(state: AutocodeState) -> dict:
    """[v2.0] Run fresh pytest on autocode test files.

    Returns partial state update with:
      - test_results: dict with {success, stdout, stderr, returncode}
      - tests_passed: bool (True if pytest exit code 0)

    If no test files exist, skips pytest (was: ran entire project suite).
    """
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return {}

    tracer.step(tid, "run_pytest", "running fresh pytest")

    run_path = state.get("autocode_run_path", "")
    if run_path:
        run_dir = Path(run_path)
    else:
        from workflows.autocode_impl.helpers import _get_autocode_run_path
        run_dir = _get_autocode_run_path(tid)

    test_file = run_dir / "test_autocode_feature.py"
    tests_dir = run_dir / "tests"

    # [Pre-2.0 Fix] If no test files exist, skip pytest entirely.
    if not tests_dir.exists() and not test_file.exists():
        tracer.step(tid, "run_pytest", "no test files found, skipping pytest")
        return {
            "test_results": {
                "success": False,
                "stdout": "",
                "stderr": "No test files found — skipping pytest",
                "returncode": -1,
            },
            "tests_passed": False,
        }

    # [v3.1 #41] AST/linter pre-check — run ruff --select E999 (syntax-only)
    # before pytest. If syntax errors exist, pytest would fail anyway with a
    # less clear error. This saves a ~30s pytest run and gives the debug node
    # a precise syntax error message.
    base_path = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
    files_to_check = []
    if test_file.exists():
        files_to_check.append(str(test_file))
    if tests_dir.exists():
        files_to_check.append(str(tests_dir))

    try:
        syntax_cmd = [sys.executable, "-m", "ruff", "check", "--select", "E999", "--no-cache"] + files_to_check
        syntax_result = subprocess.run(syntax_cmd, capture_output=True, text=True, timeout=10, encoding='utf-8', cwd=str(base_path))
        if syntax_result.returncode != 0:
            # Syntax errors found — skip pytest, return the error directly
            syntax_error = syntax_result.stdout.strip() or syntax_result.stderr.strip()
            tracer.step(tid, "run_pytest", f"SYNTAX ERROR (ruff E999): {syntax_error[:200]}")
            return {
                "test_results": {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Syntax error detected (ruff E999):\n{syntax_error[:1000]}",
                    "returncode": -1,
                },
                "tests_passed": False,
                "_pytest_output": f"Syntax error (ruff E999):\n{syntax_error[:2000]}",
            }
    except FileNotFoundError:
        # ruff not installed — skip pre-check, run pytest directly
        tracer.step(tid, "run_pytest", "ruff not found, skipping syntax pre-check")
    except subprocess.TimeoutExpired:
        tracer.step(tid, "run_pytest", "ruff syntax pre-check timed out, skipping")
    except Exception as e:
        tracer.step(tid, "run_pytest", f"ruff pre-check error (non-fatal): {e}")

    try:
        cmd = [sys.executable, "-m", "pytest", "--tb=short", "--color=no", "-q"]
        if tests_dir.exists():
            cmd.append(str(tests_dir))
        if test_file.exists():
            cmd.append(str(test_file))

        # Run from project root so imports resolve correctly
        # [v3.1 #41] base_path already computed above for ruff pre-check
        # [v1.4 P1] Use cfg.sandbox_timeout instead of hardcoded 120s.
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg.sandbox_timeout, encoding='utf-8', cwd=str(base_path))
        fresh_output = (result.stdout + result.stderr).strip()
        tests_passed = result.returncode == 0

        tracer.step(tid, "run_pytest", f"pytest {'PASS' if tests_passed else 'FAIL'} (exit {result.returncode})")

        return {
            "test_results": {
                "success": tests_passed,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            },
            "tests_passed": tests_passed,
            # Stash fresh output for LLM review node (not in state schema, ephemeral)
            "_pytest_output": fresh_output[:2000],
        }
    except FileNotFoundError:
        return {
            "test_results": {
                "success": False,
                "stdout": "",
                "stderr": "pytest not found in PATH — install with: pip install pytest",
                "returncode": -1,
            },
            "tests_passed": False,
            "_pytest_output": "pytest not found in PATH — install with: pip install pytest",
        }
    except subprocess.TimeoutExpired as e:
        return {
            "test_results": {
                "success": False,
                "stdout": "",
                "stderr": f"pytest timed out after {e.timeout}s",
                "returncode": -1,
            },
            "tests_passed": False,
            "_pytest_output": f"pytest timed out after {e.timeout}s",
        }
    except Exception as e:
        return {
            "test_results": {
                "success": False,
                "stdout": "",
                "stderr": f"pytest failed to run: {e}",
                "returncode": -1,
            },
            "tests_passed": False,
            "_pytest_output": f"pytest failed to run: {e}",
        }
