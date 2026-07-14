"""tests/workflows/autocode/test_execute.py
Tests for node_execute_step and node_write_files.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch
from pathlib import Path


class TestNodeExecuteStep:
    def test_reads_plan_and_calls_llm(self, base_state):
        from workflows.autocode_impl.nodes.execute import node_execute_step
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
            mock_call.return_value = "def helper(): pass"
            result = node_execute_step(base_state)
            assert result["tdd_source_code"] == "def helper(): pass"
            assert "execution_notes" in result

    def test_empty_plan_returns_error(self):
        from workflows.autocode_impl.nodes.execute import node_execute_step
        # [v2.2] Include plan_state sub-state so accessor finds the empty plan
        state = {"task": "empty plan", "trace_id": "t1", "status": "running",
                 "plan": [], "current_step": 0,
                 "plan_state": {"plan": [], "current_step": 0, "spec": "", "brainstorm_notes": "", "plan_accepted": False}}
        result = node_execute_step(state)
        assert result["status"] == "error"
        assert "No more plan steps" in result["error"]

    def test_respects_dry_run(self, base_state):
        from workflows.autocode_impl.nodes.execute import node_execute_step
        base_state["dry_run"] = True
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
            mock_call.return_value = "print('dry')"
            result = node_execute_step(base_state)
            assert "modified_files" not in result

    def test_increments_current_step(self, base_state):
        from workflows.autocode_impl.nodes.execute import node_execute_step
        # [v2.2] Override plan in BOTH sub-state + flat field (accessor reads sub-state first)
        test_plan = [
            {"id": 1, "label": "write_code", "description": "step 1"},
            {"id": 2, "label": "write_code", "description": "step 2"},
        ]
        base_state["plan"] = test_plan  # flat mirror
        base_state["plan_state"]["plan"] = test_plan  # sub-state (primary)
        base_state["plan_state"]["current_step"] = 0
        base_state["current_step"] = 0
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
            mock_call.return_value = "code"
            result = node_execute_step(base_state)
            assert result["current_step"] == 1

    def test_does_not_increment_beyond_plan(self, base_state):
        """When current_step >= len(plan), return error (no increment)."""
        from workflows.autocode_impl.nodes.execute import node_execute_step
        # [v2.2] Override plan + current_step in BOTH sub-state + flat field
        test_plan = [{"id": 1, "label": "write_code", "description": "only step"}]
        base_state["plan"] = test_plan  # flat mirror
        base_state["plan_state"]["plan"] = test_plan  # sub-state (primary)
        base_state["plan_state"]["current_step"] = 1
        base_state["current_step"] = 1
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
            mock_call.return_value = "code"
            result = node_execute_step(base_state)
            # current_step=1 with 1-element plan → "No more plan steps" error
            assert result["status"] == "error"
            assert "No more plan steps" in result["error"]


class TestNodeWriteFiles:
    def test_skips_on_missing_tdd_source_code(self, base_state):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        base_state.pop("tdd_source_code", None)
        assert node_write_files(base_state) == {}

    def test_parses_json_and_writes(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        payload = {"new_files": {"test_output.py": "# generated"}}
        base_state["tdd_source_code"] = json.dumps(payload)
        base_state["dry_run"] = False
        base_state["test_code"] = "def test_feature(): assert True"
        result = node_write_files(base_state)
        assert (temp_workspace / "test_output.py").exists()
        assert (temp_workspace / "test_output.py").read_text() == "# generated"
        assert "autocode_run_path" in result
        assert "test_files" in result

    def test_invalid_json_returns_error(self, base_state):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        base_state["tdd_source_code"] = "{ invalid json"
        result = node_write_files(base_state)
        assert result.get("status") == "error"
        assert "JSON parse" in result.get("error", "")

    def test_populates_test_files_when_test_code_present(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        payload = {"new_files": {"out.py": "# code"}}
        base_state["tdd_source_code"] = json.dumps(payload)
        base_state["dry_run"] = False
        base_state["test_code"] = "def test_feature(): assert True"
        result = node_write_files(base_state)
        assert len(result.get("test_files", [])) > 0

    def test_no_test_files_when_no_test_code(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        payload = {"new_files": {"out.py": "# code"}}
        base_state["tdd_source_code"] = json.dumps(payload)
        base_state["dry_run"] = False
        base_state["test_code"] = ""
        result = node_write_files(base_state)
        assert result.get("test_files", []) == []

    def test_populates_files_map(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        payload = {"new_files": {"out.py": "# code"}}
        base_state["tdd_source_code"] = json.dumps(payload)
        base_state["dry_run"] = False
        base_state["test_code"] = ""
        result = node_write_files(base_state)
        assert "files_map" in result
        assert len(result["files_map"]) > 0

    def test_no_bak_files_created(self, base_state, temp_workspace):
        """[Bug #1] Atomic writes only — no .bak files."""
        from workflows.autocode_impl.nodes.write_files import node_write_files
        payload = {"new_files": {"nobak.py": "# code"}}
        base_state["tdd_source_code"] = json.dumps(payload)
        base_state["dry_run"] = False
        base_state["test_code"] = ""
        node_write_files(base_state)
        assert not list(temp_workspace.glob("*.bak")), "No .bak files must be created"


class TestTestCodeListCoercion:
    def test_list_joined_to_string(self, base_state, temp_workspace):
        """test_code as list must be joined to a string for writing."""
        from workflows.autocode_impl.nodes.write_files import node_write_files
        payload = {"new_files": {"out.py": "# code"}}
        base_state["tdd_source_code"] = json.dumps(payload)
        base_state["dry_run"] = False
        base_state["test_code"] = ["def test_a(): assert True", "def test_b(): assert True"]
        result = node_write_files(base_state)
        assert len(result.get("test_files", [])) > 0
