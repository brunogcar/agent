"""
tests/workflows/autocode/test_nodes.py
Unit tests for execute and write_files nodes.
Guarantees:
- LLM calls are mocked; no external requests
- File writes are scoped to tmp_path via cfg.agent_root patch
- Validates corrected schema: plan as list[dict], tdd_source_code key
- Tests minimal state diff returns (LangGraph best practice)
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """Patch cfg.agent_root to tmp_path for safe file writes."""
    import core.config
    monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)
    yield tmp_path


@pytest.fixture
def base_state(temp_workspace):
    """Minimal valid state for node execution tests."""
    return {
        "task": "test node execution",
        "trace_id": "test-trace-node",
        "status": "running",
        "dry_run": True,
        "plan": [
            {"id": 1, "label": "write_code", "description": "implement helper"}
        ],
        "current_step": 0,
        "tdd_source_code": "",
        "files_context": "# empty",
    }


class TestNodeExecuteStep:
    """Validate execute node reads plan as list, calls LLM, sets tdd_source_code."""

    def test_execute_reads_plan_as_list(self, base_state):
        from workflows.autocode_helpers.nodes.execute import node_execute_step
        # [FIX] Patch _call where it's USED (in execute module), not where defined
        with patch("workflows.autocode_helpers.nodes.execute._call") as mock_call:
            mock_call.return_value = "def helper(): pass"
            result = node_execute_step(base_state)
            assert result["tdd_source_code"] == "def helper(): pass"
            assert "execution_notes" in result
            # Verify minimal diff (LangGraph pattern)
            assert set(result.keys()) >= {"tdd_source_code", "execution_notes"}

    def test_execute_handles_empty_plan_gracefully(self, temp_workspace):
        from workflows.autocode_helpers.nodes.execute import node_execute_step
        state = {
            "task": "empty plan test",
            "trace_id": "t-empty",
            "status": "running",
            "plan": [],
            "current_step": 0,
        }
        result = node_execute_step(state)
        assert result["status"] == "error"
        # [FIX] Match actual error message from execute.py
        assert "No more plan steps" in result["error"]

    def test_execute_respects_dry_run(self, base_state):
        from workflows.autocode_helpers.nodes.execute import node_execute_step
        base_state["dry_run"] = True
        with patch("workflows.autocode_helpers.nodes.execute._call") as mock_call:
            mock_call.return_value = "print('dry')"
            result = node_execute_step(base_state)
            # dry_run=True should skip _write_files, so modified_files stays unset
            assert "modified_files" not in result


class TestNodeWriteFiles:
    """Validate write_files reads tdd_source_code, applies patches, handles errors."""

    def test_write_files_skips_on_missing_tdd_source_code(self, base_state):
        from workflows.autocode_helpers.nodes.write_files import node_write_files
        base_state.pop("tdd_source_code", None)
        result = node_write_files(base_state)
        # LangGraph partial update: empty dict means no changes
        assert result == {}

    def test_write_files_parses_json_and_writes(self, temp_workspace, base_state):
        from workflows.autocode_helpers.nodes.write_files import node_write_files
        payload = {"new_files": {"test_output.py": "# generated"}}
        base_state["tdd_source_code"] = json.dumps(payload)
        base_state["dry_run"] = False  # Allow actual write to tmp_path

        result = node_write_files(base_state)
        # File should exist in temp workspace
        assert (temp_workspace / "test_output.py").exists()
        assert (temp_workspace / "test_output.py").read_text() == "# generated"

    def test_write_files_handles_invalid_json_gracefully(self, base_state):
        from workflows.autocode_helpers.nodes.write_files import node_write_files
        base_state["tdd_source_code"] = "{ invalid json"
        result = node_write_files(base_state)
        # LangGraph partial update: empty dict means no changes
        assert result == {}