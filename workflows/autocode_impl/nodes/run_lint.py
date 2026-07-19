"""[v2.0] Run lint node — ruff check on modified files only.

Split from node_verify (Phase 3.2). This node runs ruff on the modified
files only (was: entire workspace). Lint is advisory — warnings don't block
commit. pytest is handled by node_run_pytest (previous in graph).
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from workflows.autocode_impl.state import AutocodeState, _get_files  # [v2.3] accessor
from workflows.autocode_impl.helpers import _should_skip_node, is_cancellation_requested, _remaining_timeout  # [v3.6 #35]
from core.config import cfg
from core.tracer import tracer


def node_run_lint(state: AutocodeState) -> dict:
    """[v2.0] Run ruff lint on modified files only.

    Returns partial state update with:
      - lint_output: str (ruff stdout+stderr)
      - lint_passed: bool | None (None if ruff unavailable or no files)
    """
    tid = state.get("trace_id", "")
    if _should_skip_node(state):
        return {}

    # [Pre-2.0 Fix] Was: ruff check on entire workspace_root (slow, noisy).
    # Now scopes to modified_files only.
    modified_files = _get_files(state, "modified_files", [])  # [v2.3] accessor
    if not modified_files:
        tracer.step(tid, "run_lint", "no modified files to lint")
        return {"lint_output": "No modified files to lint", "lint_passed": None}

    lint_base = Path(state.get("project_root", "")) if state.get("project_root") else cfg.workspace_root
    lint_targets = [str(lint_base / f) for f in modified_files if f]
    if not lint_targets:
        return {"lint_output": "No modified files to lint", "lint_passed": None}

    # [v3.6 #35] Check cancellation before subprocess — if the graph
    # already timed out before we entered this node, bail immediately.
    if is_cancellation_requested():
        return {"lint_output": "Cancelled", "lint_passed": None}

    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check"] + lint_targets +
            ["--select", "E,F", "--no-cache"],
            capture_output=True, text=True, timeout=_remaining_timeout(30), encoding='utf-8'
        )
        lint_output = (result.stdout + result.stderr).strip()
        lint_passed = result.returncode == 0
        tracer.step(tid, "run_lint", f"ruff {'OK' if lint_passed else 'WARN'}")

        # [v3.6 #35] Check cancellation after subprocess — if the graph
        # timed out during the ruff call, discard the results.
        if is_cancellation_requested():
            return {"lint_output": "Cancelled", "lint_passed": None}

        return {
            "lint_output": lint_output[:500],
            "lint_passed": lint_passed,
        }
    except Exception as e:
        tracer.step(tid, "run_lint", f"ruff not available: {e}")
        return {
            "lint_output": f"ruff not available: {e}",
            "lint_passed": None,  # [P1 #7] Was True — missing ruff should not report as pass
        }
