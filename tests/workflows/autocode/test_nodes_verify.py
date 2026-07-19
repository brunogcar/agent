"""tests/workflows/autocode/test_nodes_verify.py — Phase 12-15 node tests.

Focused per-node tests for the verify chain nodes. Each node gets 2-3 tests
covering the happy path, error path, and skip condition.

Covers:
  - node_run_pytest      (mock subprocess, syntax error path, skip)
  - node_run_lint        (mock subprocess, missing ruff, skip)
  - node_llm_review      (mock _call, debug_summary injection, skip)
  - node_verify_decision (mock state, hallucination guard, max_retries)

LLM + subprocess + memory calls are mocked per-test — no real subprocess calls.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


def _completed_process(returncode=0, stdout="", stderr=""):
    """Build a mock CompletedProcess for subprocess.run patches."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# node_run_pytest
# ---------------------------------------------------------------------------


class TestNodeRunPytest:
    def test_skips_on_failed_status(self, base_state):
        from workflows.autocode_impl.nodes.run_pytest import node_run_pytest
        base_state["status"] = "failed"
        assert node_run_pytest(base_state) == {}

    def test_no_test_files_returns_failure(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.run_pytest import node_run_pytest
        # autocode_run_path points to an empty dir — no test file or tests dir.
        base_state["autocode_run_path"] = str(temp_workspace / "empty_run")
        (temp_workspace / "empty_run").mkdir(parents=True, exist_ok=True)
        result = node_run_pytest(base_state)
        assert result["tests_passed"] is False
        assert "No test files" in result["test_results"]["stderr"]

    def test_syntax_error_short_circuits_pytest(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.run_pytest import node_run_pytest
        run_dir = temp_workspace / "syntax_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "test_autocode_feature.py").write_text("def broken(:\n  pass\n")
        base_state["autocode_run_path"] = str(run_dir)
        # First subprocess.run call = ruff (returncode=1 syntax error).
        # Second call must NOT happen (short-circuit).
        with patch("workflows.autocode_impl.nodes.run_pytest.subprocess.run",
                   return_value=_completed_process(1, "SyntaxError: invalid syntax", "")) as mock_run:
            result = node_run_pytest(base_state)
            assert mock_run.call_count == 1  # only ruff, not pytest
        assert result["tests_passed"] is False
        assert "Syntax error" in result["test_results"]["stderr"]

    def test_passing_pytest_returns_tests_passed(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.run_pytest import node_run_pytest
        run_dir = temp_workspace / "ok_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "test_autocode_feature.py").write_text("def test_ok(): assert True\n")
        base_state["autocode_run_path"] = str(run_dir)
        with patch("workflows.autocode_impl.nodes.run_pytest.subprocess.run",
                   side_effect=[_completed_process(0, "", ""),  # ruff pre-check passes
                                _completed_process(0, "1 passed", "")]):  # pytest passes
            result = node_run_pytest(base_state)
        assert result["tests_passed"] is True
        assert result["test_results"]["success"] is True


# ---------------------------------------------------------------------------
# node_run_lint
# ---------------------------------------------------------------------------


class TestNodeRunLint:
    def test_skips_on_failed_status(self, base_state):
        from workflows.autocode_impl.nodes.run_lint import node_run_lint
        base_state["status"] = "failed"
        assert node_run_lint(base_state) == {}

    def test_no_modified_files_returns_none(self, base_state):
        from workflows.autocode_impl.nodes.run_lint import node_run_lint
        base_state["files_state"]["modified_files"] = []
        result = node_run_lint(base_state)
        assert result["lint_passed"] is None
        assert "No modified files" in result["lint_output"]

    def test_ruff_passes_returns_lint_passed_true(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.run_lint import node_run_lint
        target = temp_workspace / "mod.py"
        target.write_text("x = 1\n")
        base_state["files_state"]["modified_files"] = ["mod.py"]
        with patch("workflows.autocode_impl.nodes.run_lint.subprocess.run",
                   return_value=_completed_process(0, "All checks passed", "")):
            result = node_run_lint(base_state)
        assert result["lint_passed"] is True

    def test_ruff_missing_returns_none(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.run_lint import node_run_lint
        target = temp_workspace / "mod.py"
        target.write_text("x = 1\n")
        base_state["files_state"]["modified_files"] = ["mod.py"]
        with patch("workflows.autocode_impl.nodes.run_lint.subprocess.run",
                   side_effect=FileNotFoundError("ruff not found")):
            result = node_run_lint(base_state)
        # [P1 #7] Must be None (not True) when ruff is missing.
        assert result["lint_passed"] is None


# ---------------------------------------------------------------------------
# node_llm_review
# ---------------------------------------------------------------------------


class TestNodeLlmReview:
    def test_skips_on_failed_status(self, base_state):
        from workflows.autocode_impl.nodes.llm_review import node_llm_review
        base_state["status"] = "failed"
        assert node_llm_review(base_state) == {}

    def test_returns_llm_review_data(self, base_state):
        from workflows.autocode_impl.nodes.llm_review import node_llm_review
        payload = {"automated_checks_passed": True, "checks": {}, "summary": "ok"}
        with patch("workflows.autocode_impl.nodes.llm_review._call") as mock_call:
            mock_call.return_value = json.dumps(payload)
            result = node_llm_review(base_state)
        assert result["llm_review_data"]["automated_checks_passed"] is True

    def test_injects_debug_summary_when_history_long(self, base_state):
        from workflows.autocode_impl.nodes.llm_review import node_llm_review
        base_state["tdd"]["debug_summary"] = "compressed summary of debug"
        base_state["tdd"]["debug_history"] = [{"iteration": i} for i in range(6)]
        with patch("workflows.autocode_impl.nodes.llm_review._call") as mock_call:
            mock_call.return_value = '{"automated_checks_passed": false, "checks": {}, "summary": ""}'
            node_llm_review(base_state)
        _, kwargs = mock_call.call_args
        assert "DEBUG SUMMARY" in kwargs["user"]
        assert "compressed summary" in kwargs["user"]

    def test_llm_exception_returns_default_failure(self, base_state):
        from workflows.autocode_impl.nodes.llm_review import node_llm_review
        with patch("workflows.autocode_impl.nodes.llm_review._call",
                   side_effect=RuntimeError("LLM down")):
            result = node_llm_review(base_state)
        # Exception handler must populate default failure data, NOT raise.
        assert result["llm_review_data"]["automated_checks_passed"] is False
        assert "error" in result["llm_review_data"]["summary"].lower()


# ---------------------------------------------------------------------------
# node_verify_decision
# ---------------------------------------------------------------------------


class TestNodeVerifyDecision:
    def test_skips_on_failed_status(self, base_state):
        from workflows.autocode_impl.nodes.verify_decision import node_verify_decision
        base_state["status"] = "failed"
        base_state["tdd"]["status"] = ""  # ensure not max_retries
        assert node_verify_decision(base_state) == {}

    def test_passes_when_all_checks_ok(self, base_state):
        from workflows.autocode_impl.nodes.verify_decision import node_verify_decision
        base_state["tests_passed"] = True
        base_state["llm_review_data"] = {
            "automated_checks_passed": True,
            "checks": {
                "syntax": {"passed": True}, "tests": {"passed": True},
                "spec": {"passed": True}, "regressions": {"passed": True},
                "cleanliness": {"passed": True},
            },
            "summary": "all good",
        }
        result = node_verify_decision(base_state)
        assert result["verify"]["passed"] is True

    def test_hallucination_guard_blocks_false_pass_claim(self, base_state):
        """LLM claims tests passed but pytest actually failed — verify must fail."""
        from workflows.autocode_impl.nodes.verify_decision import node_verify_decision
        base_state["tests_passed"] = False
        base_state["llm_review_data"] = {
            "automated_checks_passed": True,  # hallucination
            "checks": {
                "syntax": {"passed": True}, "tests": {"passed": True},
                "spec": {"passed": True}, "regressions": {"passed": True},
                "cleanliness": {"passed": True},
            },
            "summary": "looks ok",
        }
        result = node_verify_decision(base_state)
        # Real pytest failure must override the LLM claim — verify.passed=False.
        assert result["verify"]["passed"] is False

    def test_max_retries_exceeded_returns_failed(self, base_state):
        from workflows.autocode_impl.nodes.verify_decision import node_verify_decision
        base_state["tdd"]["status"] = "max_retries_exceeded"
        base_state["tdd"]["error"] = "AssertionError"
        base_state["task"] = "fix bug"
        with patch("core.memory_engine.memory.store", return_value={"status": "stored"}):
            result = node_verify_decision(base_state)
        assert result["status"] == "failed"
        assert result["verify"]["passed"] is False
