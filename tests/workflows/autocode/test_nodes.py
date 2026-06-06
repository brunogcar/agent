"""tests/workflows/autocode/test_nodes.py
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
    """Patch cfg.workspace_root to tmp_path for safe file writes."""
    import core.config
    monkeypatch.setattr(core.config.cfg, "workspace_root", tmp_path)
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
        "project_root": str(temp_workspace),
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
        base_state["dry_run"] = False
        base_state["test_code"] = "def test_feature(): assert True"

        result = node_write_files(base_state)
        # File should exist in temp workspace
        assert (temp_workspace / "test_output.py").exists()
        assert (temp_workspace / "test_output.py").read_text() == "# generated"

        # Test file should be in per-run autocode directory
        assert "autocode_run_path" in result
        run_path = Path(result["autocode_run_path"])
        test_file = run_path / "test_autocode_feature.py"
        assert test_file.exists()
        assert "test_feature" in test_file.read_text()

        # generated_code.json should exist
        assert (run_path / "generated_code.json").exists()

        # test_files should contain relative path
        assert "test_files" in result
        assert result["test_files"][0].endswith("/test_autocode_feature.py")
        assert result["test_files"][0].startswith("autocode/")

    def test_write_files_handles_invalid_json_gracefully(self, base_state):
        from workflows.autocode_helpers.nodes.write_files import node_write_files
        base_state["tdd_source_code"] = "{ invalid json"
        result = node_write_files(base_state)
        # LangGraph partial update: empty dict means no changes
        assert result == {}

class TestAutocodePathHelpers:
    """Validate per-run autocode directory structure and cleanup."""

    def test_get_autocode_run_path_creates_directory(self, temp_workspace):
        from workflows.autocode_helpers.helpers import _get_autocode_run_path
        run_dir = _get_autocode_run_path("test-trace-123")
        assert run_dir.exists()
        assert run_dir.name == "test-trace-123"
        # Should be under workspace/autocode/YYYYMMDD/
        assert run_dir.parent.parent.name == "autocode"
        assert run_dir.parent.parent.parent == temp_workspace

    def test_cleanup_old_autocode_runs_removes_stale_dirs(self, temp_workspace, monkeypatch):
        from workflows.autocode_helpers.helpers import _cleanup_old_autocode_runs
        import shutil
        from datetime import datetime, timedelta
        import core.tracer
        monkeypatch.setattr(core.tracer.tracer, "step", lambda *args, **kwargs: None)

        # Create an old run directory
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
        old_dir = temp_workspace / "autocode" / old_date / "old-trace"
        old_dir.mkdir(parents=True, exist_ok=True)
        (old_dir / "test.py").write_text("pass", encoding="utf-8")

        # Create a recent run directory
        recent_date = datetime.now().strftime("%Y%m%d")
        recent_dir = temp_workspace / "autocode" / recent_date / "recent-trace"
        recent_dir.mkdir(parents=True, exist_ok=True)
        (recent_dir / "test.py").write_text("pass", encoding="utf-8")

        _cleanup_old_autocode_runs(max_age_days=7)

        assert not old_dir.exists(), "Old autocode dir should be cleaned up"
        assert recent_dir.exists(), "Recent autocode dir should be preserved"
