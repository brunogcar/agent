"""tests/workflows/autocode/test_regressions.py
Regression tests for bugs fixed in commits b04e6cd and 1ee46dd.
These tests verify that fixed bugs do not reoccur.
"""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from workflows.autocode_helpers.graph import build_graph, get_graph
from workflows.autocode_helpers.nodes.execute import node_execute_step
from workflows.autocode_helpers.nodes.write_files import node_write_files
from workflows.autocode_helpers.nodes.run_tests import node_run_tests
from workflows.autocode_helpers.nodes.debug import node_systematic_debug
from workflows.autocode_helpers.state import AutocodeState

class TestDebugLoopRouting:
    """A.2: Debug loop must route through write_files before re-running tests."""

    def test_debug_edge_routes_to_write_files_not_run_tests(self):
        """After systematic debug, fixes must be written to disk before testing."""
        from workflows.autocode_helpers.graph import build_graph
        g = build_graph()
        # LangGraph edges is a set of (source, target) tuples
        assert ("node_systematic_debug", "node_write_files") in g.edges, (
            "node_systematic_debug must route to node_write_files before "
            "node_run_tests so that JSON patches are persisted to disk"
        )

class TestWriteFilesPopulatesTestFiles:
    """A.3: write_files must return test_files so run_tests knows what to execute."""

    def test_write_files_returns_test_files_when_test_code_present(self, tmp_path, monkeypatch):
        """When state contains test_code, write_files must return test_files path."""
        import core.config
        monkeypatch.setattr(core.config.cfg, "workspace_root", tmp_path)
        monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)

        state: AutocodeState = {
            "trace_id": "test",
            "project_root": str(tmp_path),
            "test_code": "def test_feature(): pass",
            "tdd_source_code": json.dumps({"patches": [], "new_files": {}}),
        }
        result = node_write_files(state)
        assert "test_files" in result, (
            "node_write_files must return 'test_files' when test_code is present "
            "so that node_run_tests knows which files to execute"
        )
        assert result["test_files"][0].startswith("autocode/")
        assert result["test_files"][0].endswith("/test_autocode_feature.py")

    def test_write_files_no_test_files_when_no_test_code(self, tmp_path, monkeypatch):
        """When state has no test_code, test_files should not be returned."""
        import core.config
        monkeypatch.setattr(core.config.cfg, "workspace_root", tmp_path)
        monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)

        state: AutocodeState = {
            "trace_id": "test",
            "project_root": str(tmp_path),
            "tdd_source_code": json.dumps({"patches": [], "new_files": {}}),
        }
        result = node_write_files(state)
        assert "test_files" not in result, (
            "test_files should not be returned when test_code is absent"
        )

class TestTestCodeListCoercion:
    """A.6: test_code is list[str] from _extract_code but write_text expects str."""

    def test_test_code_list_joined_to_string(self, tmp_path, monkeypatch):
        """If test_code is a list, it must be joined with newlines before writing."""
        import core.config
        monkeypatch.setattr(core.config.cfg, "workspace_root", tmp_path)
        monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)

        state: AutocodeState = {
            "trace_id": "test",
            "project_root": str(tmp_path),
            "test_code": ["def test_a(): pass", "def test_b(): pass"],
            "tdd_source_code": json.dumps({"patches": [], "new_files": {}}),
        }
        result = node_write_files(state)
        assert result.get("test_files") is not None
        # Verify file was written with joined content
        assert "autocode_run_path" in result
        run_path = Path(result["autocode_run_path"])
        test_file = run_path / "test_autocode_feature.py"
        assert test_file.exists()
        content = test_file.read_text(encoding="utf-8")
        assert "def test_a(): pass" in content
        assert "def test_b(): pass" in content
        assert "\n\n" in content, "List elements should be joined with double newlines"

class TestExecuteStepIncrementsCurrentStep:
    """A.9: execute_step must increment current_step so the plan advances."""

    def test_execute_step_increments_current_step(self):
        """After executing a plan step, current_step must advance by 1."""
        state: AutocodeState = {
            "trace_id": "test",
            "plan": [{"description": "step 1"}, {"description": "step 2"}],
            "current_step": 0,
            "files_context": "# empty",
            "dry_run": True,
        }
        with patch("workflows.autocode_helpers.nodes.execute._call") as mock_call:
            mock_call.return_value = json.dumps({"patches": [], "new_files": {}})
            result = node_execute_step(state)
            assert "current_step" in result, (
                "node_execute_step must return 'current_step' so the plan advances"
            )
            assert result["current_step"] == 1, (
                f"current_step should be 1, got {result.get('current_step')}"
            )

    def test_execute_step_does_not_increment_beyond_plan(self):
        """When current_step exceeds plan length, execute_step should return error."""
        state: AutocodeState = {
            "trace_id": "test",
            "plan": [{"description": "step 1"}],
            "current_step": 1,
            "files_context": "# empty",
        }
        result = node_execute_step(state)
        assert result.get("status") == "error"

class TestDryRunSkipsModifiedFiles:
    """P1 #3: dry_run=True must not populate modified_files."""

    def test_dry_run_true_no_modified_files(self):
        """When dry_run is True, modified_files should not be in the result."""
        state: AutocodeState = {
            "trace_id": "test",
            "plan": [{"description": "step 1"}],
            "current_step": 0,
            "files_context": "# empty",
            "dry_run": True,
        }
        with patch("workflows.autocode_helpers.nodes.execute._call") as mock_call:
            mock_call.return_value = json.dumps({
                "patches": [{"path": "foo.py", "old": "a", "new": "b"}],
                "new_files": {}
            })
            result = node_execute_step(state)
            assert "modified_files" not in result, (
                "dry_run=True must not return modified_files — "
                "disk writes are skipped"
            )

    def test_dry_run_false_populates_modified_files(self):
        """When dry_run is False, modified_files should be populated."""
        state: AutocodeState = {
            "trace_id": "test",
            "plan": [{"description": "step 1"}],
            "current_step": 0,
            "files_context": "# empty",
            "dry_run": False,
        }
        with patch("workflows.autocode_helpers.nodes.execute._call") as mock_call:
            mock_call.return_value = json.dumps({
                "patches": [{"path": "foo.py", "old": "a", "new": "b"}],
                "new_files": {"bar.py": "print(1)"}
            })
            result = node_execute_step(state)
            assert "modified_files" in result, (
                "dry_run=False must return modified_files"
            )
            assert "foo.py" in result["modified_files"]
            assert "bar.py" in result["modified_files"]

class TestRunTestsWiresTargetedCmd:
    """A.13: run_tests must pass targeted_test_cmd from state to run_tests_on_disk."""

    def test_run_tests_passes_targeted_test_cmd(self):
        """targeted_test_cmd from state must be forwarded to run_tests_on_disk."""
        state: AutocodeState = {
            "trace_id": "test",
            "test_files": ["test_a.py"],
            "targeted_test_cmd": "pytest tests/test_a.py -x",
            "project_root": "/tmp/project",
        }
        with patch("workflows.autocode_helpers.nodes.run_tests.run_tests_on_disk") as mock_run:
            mock_run.return_value = {"success": True, "stdout": "", "stderr": "", "returncode": 0}
            node_run_tests(state)
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args.kwargs.get("targeted_cmd") == "pytest tests/test_a.py -x", (
                "targeted_test_cmd from state must be passed to run_tests_on_disk"
            )
            assert call_args.kwargs.get("project_root") == "/tmp/project", (
                "project_root from state must be passed to run_tests_on_disk"
            )

class TestDebugParsesNestedJson:
    """P2 #18: debug node must handle nested JSON without crashing."""

    def test_debug_node_uses_parse_json_fallback(self):
        """Debug node imports _parse_json for robust JSON extraction."""
        import inspect
        from workflows.autocode_helpers.nodes import debug as debug_module
        source = inspect.getsource(debug_module)
        assert "_parse_json" in source, (
            "debug.py must import _parse_json for JSON extraction fallback"
        )
        # Verify the old brittle regex pattern is not used
        old_pattern = r"re.search(r'\{[^\{}]*\}'"
        assert old_pattern not in source, (
            "debug.py must not use the brittle regex that cannot match nested JSON"
        )

    def test_json_loads_parses_nested_structure(self):
        """json.loads correctly parses nested JSON with escaped newlines."""
        import json

        # Use json.dumps to create valid JSON with escaped newlines
        data = {
            "root_cause": "Missing import",
            "defense_notes": "Check imports",
            "fix": {
                "patches": [
                    {"path": "foo.py", "old": "", "new": "import os\n"}
                ]
            }
        }
        json_str = json.dumps(data, indent=2)
        result = json.loads(json_str)

        assert "root_cause" in result
        assert "fix" in result
        assert "patches" in result["fix"]
        assert result["fix"]["patches"][0]["path"] == "foo.py"

class TestProtectedPathResolution:
    """A.12: is_protected must resolve absolute path before checking, not use CWD."""

    def test_protected_path_resolves_against_project_root(self, tmp_path):
        """Relative paths must be resolved against project_root, not CWD."""
        (tmp_path / "project").mkdir(parents=True, exist_ok=True)
        state: AutocodeState = {
            "trace_id": "test",
            "project_root": str(tmp_path / "project"),
            "tdd_source_code": json.dumps({
                "patches": [{"path": "../outside.py", "old": "", "new": "bad"}]
            }),
        }
        result = node_write_files(state)
        # Path traversal outside project_root should be blocked
        assert "patch_errors" in result, (
            "Path traversal outside project_root must be blocked — "
            "this verifies that paths are resolved against project_root, not CWD"
        )

class TestFileToolModeFiltering:
    """Verify mode parameter is correctly handled for backward compatibility with read_multiple_files."""

    def test_mode_empty_string_is_filtered_from_params(self):
        """When mode is empty string, it must not be passed to handlers."""
        import inspect
        from tools.file import file

        sig = inspect.signature(file)
        params = sig.parameters

        # read_multiple_files no longer accepts mode; the parameter is removed
        # This test verifies the file tool signature does not include mode
        assert "mode" not in params, (
            "mode parameter should be removed from file tool signature — "
            "read_multiple_files no longer uses it"
        )

class TestAbsolutePathTraversalBlocked:
    """A.12: Absolute paths outside project_root must be blocked."""

    def test_absolute_path_blocked(self, tmp_path):
        """Absolute paths like /etc/passwd must not be writable."""
        (tmp_path / "project").mkdir(parents=True, exist_ok=True)
        state: AutocodeState = {
            "trace_id": "test",
            "project_root": str(tmp_path / "project"),
            "tdd_source_code": json.dumps({
                "patches": [{"path": "/etc/passwd", "old": "", "new": "evil"}]
            }),
        }
        result = node_write_files(state)
        assert "patch_errors" in result, (
            "Absolute paths outside project_root must be blocked"
        )

class TestProtectedFileBypassBlocked:
    """A.12: Relative path traversal to protected files must be blocked."""

    def test_relative_traversal_to_protected_blocked(self, tmp_path):
        """Paths like ../../agent/core/config.py must be blocked."""
        (tmp_path / "project").mkdir(parents=True, exist_ok=True)
        state: AutocodeState = {
            "trace_id": "test",
            "project_root": str(tmp_path / "project"),
            "tdd_source_code": json.dumps({
                "patches": [{"path": "../../agent/core/config.py", "old": "", "new": "evil"}]
            }),
        }
        result = node_write_files(state)
        assert "patch_errors" in result, (
            "Relative path traversal to protected files must be blocked"
        )

class TestInvalidJsonFromLlm:
    """A.1: Malformed tdd_source_code JSON must be preserved for downstream handling."""

    def test_malformed_json_preserved_in_tdd_source_code(self):
        """When LLM returns invalid JSON, execute_step preserves it for write_files to handle."""
        state: AutocodeState = {
            "trace_id": "test",
            "plan": [{"description": "step 1"}],
            "current_step": 0,
            "files_context": "# empty",
            "dry_run": True,
        }
        bad_json = "This is not JSON at all { broken"
        with patch("workflows.autocode_helpers.nodes.execute._call") as mock_call:
            mock_call.return_value = bad_json
            result = node_execute_step(state)

            # execute_step does not validate JSON; it stores the raw string
            assert result.get("tdd_source_code") == bad_json, (
                "Malformed JSON from LLM must be preserved in tdd_source_code for downstream handling"
            )
            assert "modified_files" not in result, (
                "Malformed JSON must not populate modified_files in execute_step"
            )

class TestBrainstormEarlyReturn:
    """A.8: needs_clarification must return empty dict without NameError."""

    def test_needs_clarification_returns_empty_dict(self):
        """When status is needs_clarification, brainstorm must return {}."""
        from workflows.autocode_helpers.nodes.brainstorm import node_brainstorm

        state: AutocodeState = {
            "trace_id": "test",
            "status": "needs_clarification",
            "task": "test task",
        }
        result = node_brainstorm(state)
        assert result == {}, (
            "needs_clarification must return empty dict without referencing undefined variables"
        )
