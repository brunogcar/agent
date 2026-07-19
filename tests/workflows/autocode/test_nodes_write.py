"""tests/workflows/autocode/test_nodes_write.py — Phase 8a-8c + summarize node tests.

Focused per-node tests for the write pipeline nodes. Each node gets 2-3 tests
covering the happy path, error path, and skip condition.

Covers:
  - node_apply_patches     (mock apply_patch, dry_run validation, skip)
  - node_write_new_files   (file writes, dry_run skip, missing source)
  - node_persist_artifacts (test file write, list coercion, skip)
  - node_summarize_context (empty history, long history, symbol offload)

LLM + file writes are mocked per-test where needed — most paths are real
filesystem operations under tmp_path.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# node_apply_patches
# ---------------------------------------------------------------------------


class TestNodeApplyPatches:
    def test_skips_on_failed_status(self, base_state):
        from workflows.autocode_impl.nodes.apply_patches import node_apply_patches
        base_state["status"] = "failed"
        assert node_apply_patches(base_state) == {}

    def test_skips_when_no_source_code(self, base_state):
        from workflows.autocode_impl.nodes.apply_patches import node_apply_patches
        # Default base_state has empty tdd.source_code.
        assert node_apply_patches(base_state) == {}

    def test_json_parse_error_returns_error_status(self, base_state):
        from workflows.autocode_impl.nodes.apply_patches import node_apply_patches
        base_state["tdd"]["source_code"] = "not valid json {{{"
        result = node_apply_patches(base_state)
        assert result["status"] == "error"
        assert "JSON parse" in result["error"]

    def test_dry_run_runs_validation_but_skips_apply(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.apply_patches import node_apply_patches
        # Patch targets a missing file — dry_run must record the error but
        # NOT call apply_patch (the actual disk operation).
        target_rel = "missing.py"
        base_state["tdd"]["source_code"] = json.dumps({
            "patches": [{"path": target_rel, "old": "a", "new": "b"}],
        })
        base_state["dry_run"] = True
        with patch("workflows.autocode_impl.patch.apply_patch") as mock_apply:
            result = node_apply_patches(base_state)
            mock_apply.assert_not_called()
        assert result["status"] == "dry_run"
        # modified_files is empty (no patch was applied).
        assert result["files_state"]["modified_files"] == []
        # patch_errors records the missing-file validation failure.
        assert any(target_rel in e for e in result.get("patch_errors", []))

    def test_applies_patch_and_records_modified_file(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.apply_patches import node_apply_patches
        target = temp_workspace / "real.py"
        target.write_text("def old(): pass\n")
        base_state["tdd"]["source_code"] = json.dumps({
            "patches": [{"path": "real.py", "old": "def old(): pass\n", "new": "def new(): return True\n"}],
        })
        result = node_apply_patches(base_state)
        assert "real.py" in result["files_state"]["modified_files"]
        assert "def new():" in target.read_text()


# ---------------------------------------------------------------------------
# node_write_new_files
# ---------------------------------------------------------------------------


class TestNodeWriteNewFiles:
    def test_skips_on_failed_status(self, base_state):
        from workflows.autocode_impl.nodes.write_new_files import node_write_new_files
        base_state["status"] = "failed"
        assert node_write_new_files(base_state) == {}

    def test_skips_when_no_source_code(self, base_state):
        from workflows.autocode_impl.nodes.write_new_files import node_write_new_files
        assert node_write_new_files(base_state) == {}

    def test_dry_run_skips_writes(self, base_state):
        from workflows.autocode_impl.nodes.write_new_files import node_write_new_files
        base_state["tdd"]["source_code"] = json.dumps({"new_files": {"out.py": "# x"}})
        base_state["dry_run"] = True
        assert node_write_new_files(base_state) == {}

    def test_writes_new_file_and_populates_files_map(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.write_new_files import node_write_new_files
        base_state["tdd"]["source_code"] = json.dumps({"new_files": {"new_module.py": "# generated"}})
        result = node_write_new_files(base_state)
        assert (temp_workspace / "new_module.py").exists()
        assert (temp_workspace / "new_module.py").read_text() == "# generated"
        assert "new_module.py" in result["files_state"]["files_map"]
        assert "new_module.py" in result["files_state"]["modified_files"]


# ---------------------------------------------------------------------------
# node_persist_artifacts
# ---------------------------------------------------------------------------


class TestNodePersistArtifacts:
    def test_skips_on_failed_status(self, base_state):
        from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts
        base_state["status"] = "failed"
        assert node_persist_artifacts(base_state) == {}

    def test_skips_when_no_test_code(self, base_state):
        from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts
        # Default base_state has empty test_code.
        assert node_persist_artifacts(base_state) == {}

    def test_dry_run_skips_persistence(self, base_state):
        from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts
        base_state["test_code"] = "def test_x(): assert True"
        base_state["dry_run"] = True
        assert node_persist_artifacts(base_state) == {}

    def test_writes_test_file_and_returns_paths(self, base_state):
        from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts
        base_state["test_code"] = "def test_x(): assert True"
        result = node_persist_artifacts(base_state)
        assert len(result["test_files"]) == 1
        assert result["test_files"][0].endswith("test_autocode_feature.py")
        assert result["autocode_run_path"]

    def test_list_test_code_is_joined_to_string(self, base_state):
        from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts
        base_state["test_code"] = ["def test_a(): pass", "def test_b(): pass"]
        result = node_persist_artifacts(base_state)
        # File must exist with both test functions (joined by \n\n).
        from pathlib import Path
        test_path = Path(result["autocode_run_path"]) / "test_autocode_feature.py"
        written = test_path.read_text()
        assert "test_a" in written and "test_b" in written
        assert "\n\n" in written


# ---------------------------------------------------------------------------
# node_summarize_context
# ---------------------------------------------------------------------------


class TestNodeSummarizeContext:
    def test_empty_history_returns_empty_summary(self, base_state):
        from workflows.autocode_impl.nodes.summarize_context import node_summarize_context
        base_state["tdd"]["debug_history"] = []
        result = node_summarize_context(base_state)
        assert result["tdd"]["debug_summary"] == ""
        # No offload ref when history is empty.
        assert "debug_history_ref" not in result["tdd"]

    def test_short_history_produces_summary_without_offload(self, base_state):
        from workflows.autocode_impl.nodes.summarize_context import node_summarize_context
        base_state["tdd"]["debug_history"] = [
            {"iteration": 1, "phase": "investigation", "root_cause": "x", "fix": "y", "tests_passed": False},
            {"iteration": 2, "phase": "fix", "root_cause": "x", "fix": "z", "tests_passed": True},
        ]
        result = node_summarize_context(base_state)
        assert result["tdd"]["debug_summary"]  # non-empty
        # 2 entries < 5 threshold → no offload.
        assert "debug_history_ref" not in result["tdd"]

    def test_long_history_triggers_symbol_offload(self, base_state):
        from workflows.autocode_impl.nodes.summarize_context import node_summarize_context
        base_state["tdd"]["debug_history"] = [
            {"iteration": i, "phase": "fix", "root_cause": f"rc{i}", "fix": f"f{i}", "tests_passed": False}
            for i in range(6)
        ]
        with patch("workflows.autocode_impl.nodes.summarize_context.offload_to_file",
                   return_value={"_symbol_ref": "debug_history", "_symbol_file": "/tmp/x.json"}) as mock_offload:
            result = node_summarize_context(base_state)
            mock_offload.assert_called_once()
        assert result["tdd"]["debug_summary"]
        assert result["tdd"]["debug_history_ref"]["_symbol_ref"] == "debug_history"
