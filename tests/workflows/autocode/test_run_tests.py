"""tests/workflows/autocode/test_run_tests.py
Tests for node_run_tests — test execution, stuck detection (#39),
budget tracking, and file-existence checks.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


# ─── Stuck detection (#39) ──────────────────────────────────────────────────

class TestStuckDetection:
    """[#39] Same error signature on consecutive iterations → bail to verify."""

    def test_error_signature_extracts_last_3_lines(self):
        from workflows.autocode_impl.nodes.run_tests import _error_signature
        assert _error_signature("line1\nline2\nline3\nline4\nline5") == "line3\nline4\nline5"

    def test_error_signature_empty(self):
        from workflows.autocode_impl.nodes.run_tests import _error_signature
        assert _error_signature("") == ""
        assert _error_signature("   ") == ""

    def test_stuck_sets_tdd_status_stuck(self, mocker):
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        same_error = "AssertionError: expected 5 got 3\n  assert x == 5\n  where x = 3"
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": False, "stderr": same_error, "stdout": ""},
        )
        state = {
            "test_files": ["test_x.py"], "tdd_iteration": 1,
            "last_test_error": same_error, "trace_id": "t1",
        }
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "stuck"

    def test_different_error_does_not_trigger_stuck(self, mocker):
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": False, "stderr": "NEW error", "stdout": ""},
        )
        state = {
            "test_files": ["test_x.py"], "tdd_iteration": 1,
            "last_test_error": "OLD different error", "trace_id": "t1",
        }
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "failed"

    def test_first_failure_does_not_trigger_stuck(self, mocker):
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": False, "stderr": "some error", "stdout": ""},
        )
        state = {
            "test_files": ["test_x.py"], "tdd_iteration": 0,
            "last_test_error": "", "trace_id": "t1",
        }
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "failed"

    def test_success_clears_last_test_error(self, mocker):
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": True, "stderr": "", "stdout": "1 passed"},
        )
        mocker.patch("core.memory_engine.memory.store")
        state = {
            "test_files": ["test_x.py"], "tdd_iteration": 2,
            "last_test_error": "old error", "trace_id": "t1",
        }
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "passed"
        assert result["last_test_error"] == ""


# ─── Test file existence checks ─────────────────────────────────────────────

class TestRunTestsFileCheck:
    def test_no_test_files_returns_error(self):
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        state = {"test_files": [], "trace_id": "t1"}
        result = node_run_tests(state)
        assert result["status"] == "error"
        assert "No test files" in result["error"]

    def test_filters_missing_files(self, mocker, tmp_path):
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        existing = tmp_path / "exists.py"
        existing.write_text("def test(): pass")
        state = {
            "test_files": ["exists.py", "missing.py"],
            "trace_id": "t1", "tdd_iteration": 0,
            "project_root": str(tmp_path),
        }
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": True, "stdout": "1 passed", "stderr": ""},
        )
        mocker.patch("core.memory_engine.memory.store")
        result = node_run_tests(state)
        # Should have run (filtered out missing.py)
        assert result["tdd_status"] == "passed"


# ─── Budget: only Tavily decrements ─────────────────────────────────────────

class TestRunTestsBudgetWiring:
    def test_targeted_cmd_passed_through(self, mocker):
        """node_run_tests must pass targeted_test_cmd to run_tests_on_disk.

        [v2.4] Simulates the post-migration state: analyze_impact writes to
        BOTH the impact sub-state AND the flat field mirror. The reader
        (run_tests) uses _get_impact accessor, which reads the sub-state
        first. Uses _default_state() to catch split-brain (Track M1
        learning #2 — the v2.0.5 split-brain bug was invisible because
        tests built state without the sub-state populated).
        """
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        from workflows.autocode_impl.state import _default_state
        mock_run = mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": True, "stdout": "", "stderr": ""},
        )
        mocker.patch("core.memory_engine.memory.store")
        mocker.patch("pathlib.Path.exists", return_value=True)
        state = _default_state(task="test", target_file="test_x.py")
        state["test_files"] = ["test_x.py"]
        state["trace_id"] = "t1"
        state["tdd_iteration"] = 0
        # Simulate what analyze_impact does post-v2.4: write to BOTH
        # sub-state (primary) and flat field (mirror). The accessor reads
        # the sub-state first — if we only set the flat field, the accessor
        # returns the sub-state default (None), not the flat value.
        cmd = "pytest tests/test_x.py"
        state["targeted_test_cmd"] = cmd  # flat mirror
        current_impact = dict(state.get("impact", {}))
        current_impact["targeted_test_cmd"] = cmd  # sub-state (primary)
        state["impact"] = current_impact
        node_run_tests(state)
        _, kwargs = mock_run.call_args
        assert kwargs.get("targeted_cmd") == cmd

    def test_targeted_cmd_read_from_impact_substate(self, mocker):
        """[v2.4] When impact sub-state has targeted_test_cmd, accessor reads it.

        This is the forward-looking test: after v2.4 migration, analyze_impact
        writes to the impact sub-state. This test verifies the reader picks up
        the sub-state value (not the stale flat-field default).
        """
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        from workflows.autocode_impl.state import _default_state
        mock_run = mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": True, "stdout": "", "stderr": ""},
        )
        mocker.patch("core.memory_engine.memory.store")
        mocker.patch("pathlib.Path.exists", return_value=True)
        state = _default_state(task="test", target_file="test_x.py")
        state["test_files"] = ["test_x.py"]
        state["trace_id"] = "t1"
        state["tdd_iteration"] = 0
        # Simulate analyze_impact having written to the impact sub-state:
        state["impact"] = {
            "warnings": [],
            "targeted_test_cmd": "pytest tests/sub/test_y.py",
            "failed": False,
        }
        # Leave the flat field as the default (None) — accessor must use sub-state
        node_run_tests(state)
        _, kwargs = mock_run.call_args
        assert kwargs.get("targeted_cmd") == "pytest tests/sub/test_y.py"
