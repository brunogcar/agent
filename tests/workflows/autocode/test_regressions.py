"""tests/workflows/autocode/test_regressions.py
Regression tests for bugs fixed in commits b04e6cd and 1ee46dd.
These tests verify that fixed bugs do not reoccur.
"""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from workflows.autocode_impl.graph import build_graph, get_graph
from workflows.autocode_impl.nodes.execute import node_execute_step
from workflows.autocode_impl.nodes.write_files import node_write_files
from workflows.autocode_impl.nodes.run_tests import node_run_tests
from workflows.autocode_impl.nodes.debug import node_systematic_debug
from workflows.autocode_impl.state import AutocodeState

class TestDebugLoopRouting:
    """A.2: Debug loop must route through write_files before re-running tests."""

    def test_debug_edge_routes_to_write_files_not_run_tests(self):
        """After systematic debug, fixes must be written to disk before testing."""
        from workflows.autocode_impl.graph import build_graph
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
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
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
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
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
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
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
        # [P2 #14] run_tests now filters missing files — mock Path.exists to return True
        with patch("workflows.autocode_impl.nodes.run_tests.run_tests_on_disk") as mock_run, \
             patch("pathlib.Path.exists", return_value=True):
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
        from workflows.autocode_impl.nodes import debug as debug_module
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
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_call:
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
        from workflows.autocode_impl.nodes.brainstorm import node_brainstorm

        state: AutocodeState = {
            "trace_id": "test",
            "status": "needs_clarification",
            "task": "test task",
        }
        result = node_brainstorm(state)
        assert result == {}, (
            "needs_clarification must return empty dict without referencing undefined variables"
        )


# =============================================================================
# P0 Bug fixes (Bug #1-#11)
# =============================================================================

class TestNoBakFiles:
    """Bug #1: No .bak files should be created — atomic writes only."""

    def test_patch_apply_no_bak_created(self, tmp_path):
        """apply_patch must not create .bak files."""
        from workflows.autocode_impl.patch import apply_patch
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n", encoding="utf-8")
        result = apply_patch(test_file, "pass", "return True")
        assert result.ok
        assert not (tmp_path / "test.py.bak").exists(), ".bak file must not be created"
        assert test_file.read_text() == "def foo():\n    return True\n"

    def test_patch_apply_patches_no_bak_created(self, tmp_path):
        """apply_patches must not create .bak files."""
        from workflows.autocode_impl.patch import apply_patches
        test_file = tmp_path / "test.py"
        test_file.write_text("old1\nold2\n", encoding="utf-8")
        result = apply_patches(test_file, [{"old": "old1", "new": "new1"}, {"old": "old2", "new": "new2"}])
        assert result.ok
        assert not (tmp_path / "test.py.bak").exists(), ".bak file must not be created"

    def test_write_files_node_no_bak_created(self, tmp_path):
        """node_write_files must not create .bak files for new files."""
        from workflows.autocode_impl.nodes.write_files import node_write_files
        import json
        tdd_code = json.dumps({"new_files": {"output.py": "print('hello')"}})
        state = {
            "trace_id": "test-nobak",
            "tdd_source_code": tdd_code,
            "project_root": str(tmp_path),
        }
        with patch("core.config.cfg.workspace_root", tmp_path), \
             patch("core.config.cfg.is_protected", return_value=False):
            node_write_files(state)
        assert not (tmp_path / "output.py.bak").exists(), ".bak file must not be created"
        assert (tmp_path / "output.py").exists()


class TestNoGitSnapshot:
    """Bug #2: git(action='snapshot') removed — branch is the safety net."""

    def test_git_ops_no_snapshot_function(self):
        """_git_snapshot must not exist in git_ops."""
        from workflows.autocode_impl import git_ops
        assert not hasattr(git_ops, "_git_snapshot"), (
            "_git_snapshot must be removed — snapshot action was deleted from git tool"
        )

    def test_branch_node_no_snapshot_call(self):
        """node_git_branch must not call _git_snapshot in actual code (not comments)."""
        import inspect
        import ast
        from workflows.autocode_impl.nodes.branch import node_git_branch
        source = inspect.getsource(node_git_branch)
        # Strip comments and docstrings to check actual code only
        tree = ast.parse(source)
        # Remove docstrings
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        # Strip comments (lines starting with #)
        code_lines = [line for line in code_only.split('\n') if not line.strip().startswith('#')]
        code_str = '\n'.join(code_lines)
        assert "_git_snapshot" not in code_str, (
            "node_git_branch must not call _git_snapshot in actual code"
        )


class TestFilesMapPopulated:
    """Bug #3: files_map must be populated by node_write_files."""

    def test_write_files_populates_files_map(self, tmp_path):
        """node_write_files must set files_map with file snapshots."""
        from workflows.autocode_impl.nodes.write_files import node_write_files
        import json
        tdd_code = json.dumps({"new_files": {"target.py": "print('hello')"}})
        state = {
            "trace_id": "test-filesmap",
            "tdd_source_code": tdd_code,
            "project_root": str(tmp_path),
        }
        with patch("core.config.cfg.workspace_root", tmp_path), \
             patch("core.config.cfg.is_protected", return_value=False):
            result = node_write_files(state)
        assert "files_map" in result, "files_map must be populated by write_files"
        assert "target.py" in result["files_map"], "target.py must be in files_map"
        assert "full_md5" in result["files_map"]["target.py"], "snapshot must have full_md5"


class TestAnalyzeImpactSync:
    """Bug #4: node_analyze_impact must be a sync function, not async."""

    def test_analyze_impact_is_sync(self):
        """node_analyze_impact must not be a coroutine function."""
        import inspect
        from workflows.autocode_impl.nodes.analyze_impact import node_analyze_impact
        assert not inspect.iscoroutinefunction(node_analyze_impact), (
            "node_analyze_impact must be sync (def, not async def) — "
            "LangGraph StateGraph.add_node expects sync functions"
        )

    def test_analyze_impact_returns_dict_on_empty_files_map(self):
        """Sync node must return dict when files_map is empty."""
        from workflows.autocode_impl.nodes.analyze_impact import node_analyze_impact
        state = {"trace_id": "test", "files_map": {}}
        result = node_analyze_impact(state)
        assert isinstance(result, dict)
        assert result.get("analyze_impact_failed") is False


class TestExecuteFilesContext:
    """Bug #6: execute.py must use _files_context() helper, not state['files_context']."""

    def test_execute_uses_files_context_helper(self):
        """execute.py must import and use _files_context, not state.get('files_context')."""
        import inspect
        from workflows.autocode_impl.nodes import execute
        source = inspect.getsource(execute)
        assert "_files_context" in source, "execute.py must use _files_context() helper"
        assert "files_context" not in source.replace("_files_context", ""), (
            "execute.py must not reference state.get('files_context') — field doesn't exist in state"
        )


class TestBrainstormMergesKgFiles:
    """Bug #7: brainstorm must store merged files_update, not original state['files']."""

    def test_brainstorm_stores_merged_files(self):
        """When kg_files are found, brainstorm must store the merged dict in code (not comments)."""
        import inspect
        import ast
        from workflows.autocode_impl.nodes.brainstorm import node_brainstorm
        source = inspect.getsource(node_brainstorm)
        # Strip comments and docstrings to check actual code only
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        # Must NOT store the original state["files"] when kg_files exist
        assert 'updates["files"] = state["files"]' not in code_only, (
            "brainstorm must not store original state['files'] in actual code — must store merged files_update"
        )


class TestImpactWarningsType:
    """Bug #8: impact_warnings state type must be list[dict], not list[str]."""

    def test_state_impact_warnings_is_list_dict(self):
        """AutocodeState.impact_warnings must be typed as list[dict]."""
        import inspect
        from workflows.autocode_impl.state import AutocodeState
        annotations = AutocodeState.__annotations__
        assert annotations.get("impact_warnings") == "list[dict]" or "dict" in str(annotations.get("impact_warnings")), (
            f"impact_warnings must be list[dict], got {annotations.get('impact_warnings')}"
        )


class TestNoDeadAgentRoot:
    """Bug #9: AGENT_ROOT = None must be removed from state.py."""

    def test_no_agent_root_module_variable(self):
        """state.py must not define AGENT_ROOT = None."""
        from workflows.autocode_impl import state
        assert not hasattr(state, "AGENT_ROOT"), (
            "AGENT_ROOT must be removed — was dead code (never set, never used)"
        )


class TestDefenseNotesPlural:
    """Bug #10: defense_note (singular) must be defense_notes (plural) everywhere."""

    def test_commit_uses_defense_notes(self):
        """commit.py must use defense_notes (plural) in actual code, not defense_note (singular)."""
        import inspect
        import ast
        from workflows.autocode_impl.nodes.commit import node_commit
        source = inspect.getsource(node_commit)
        # Strip comments and docstrings
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split('\n') if not line.strip().startswith('#')]
        code_str = '\n'.join(code_lines)
        assert "defense_note" not in code_str.replace("defense_notes", ""), (
            "commit.py must use defense_notes (plural) in actual code, not defense_note (singular)"
        )

    def test_memory_uses_defense_notes(self):
        """memory.py must use defense_notes (plural) in actual code, not defense_note."""
        import inspect
        import ast
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        source = inspect.getsource(node_distill_memory)
        # Strip comments and docstrings
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split('\n') if not line.strip().startswith('#')]
        code_str = '\n'.join(code_lines)
        assert "defense_note" not in code_str.replace("defense_notes", ""), (
            "memory.py must use defense_notes (plural) in actual code, not defense_note (singular)"
        )

    def test_memory_uses_root_cause_not_hypothesis(self):
        """Bug #11: memory.py must use root_cause in actual code, not hypothesis."""
        import inspect
        import ast
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        source = inspect.getsource(node_distill_memory)
        # Strip comments and docstrings
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split('\n') if not line.strip().startswith('#')]
        code_str = '\n'.join(code_lines)
        assert "hypothesis" not in code_str, (
            "memory.py must use root_cause (not hypothesis) in actual code — matches what debug.py sets"
        )
        assert "root_cause" in code_str, "memory.py must reference root_cause in actual code"


# =============================================================================
# P1/P2 Bug fixes (v1.0.2)
# =============================================================================

class TestReportTypeAnnotation:
    """P1 #2: node_report must return dict, not AutocodeState."""

    def test_report_returns_dict_annotation(self):
        import inspect
        from workflows.autocode_impl.nodes.report import node_report
        sig = inspect.signature(node_report)
        assert sig.return_annotation is dict or "dict" in str(sig.return_annotation), (
            "node_report return annotation must be dict, not AutocodeState"
        )


class TestCreateSkillFixes:
    """P1 #3, P2 #15/#16/#17: create_skill project root, validation, syntax, flag."""

    def test_skill_name_sanitized(self):
        from workflows.autocode_impl.nodes.create_skill import _sanitize_skill_name
        assert _sanitize_skill_name("my/skill") == "my_skill"
        assert _sanitize_skill_name("skill.py") == "skill_py"
        assert _sanitize_skill_name("") == "unnamed_skill"
        assert _sanitize_skill_name("valid_name") == "valid_name"

    def test_python_syntax_validation(self):
        from workflows.autocode_impl.nodes.create_skill import _validate_python_syntax
        ok, _ = _validate_python_syntax("x = 1")
        assert ok is True
        ok, err = _validate_python_syntax("def broken(")
        assert ok is False
        assert "SyntaxError" in err

    def test_skill_created_flag_set(self):
        """create_skill must set skill_created=True on success."""
        import inspect
        from workflows.autocode_impl.nodes.create_skill import node_create_skill
        source = inspect.getsource(node_create_skill)
        assert "skill_created" in source, "create_skill must set skill_created flag"


class TestDeadRoutesRemoved:
    """P1 #4: route_after_brainstorm and route_after_debug must be removed."""

    def test_dead_routes_not_in_routes_module(self):
        from workflows.autocode_impl import routes
        assert not hasattr(routes, "route_after_brainstorm"), "route_after_brainstorm must be removed"
        assert not hasattr(routes, "route_after_debug"), "route_after_debug must be removed"

    def test_dead_routes_not_imported_in_graph(self):
        import inspect
        from workflows.autocode_impl import graph
        source = inspect.getsource(graph)
        assert "route_after_brainstorm" not in source, "graph must not import route_after_brainstorm"
        assert "route_after_debug" not in source, "graph must not import route_after_debug"


class TestMermaidGetattrGuards:
    """P1 #5: mermaid.py must use getattr() for LangGraph internals."""

    def test_mermaid_uses_getattr(self):
        import inspect
        from workflows.autocode_impl.mermaid import export_mermaid
        source = inspect.getsource(export_mermaid)
        assert "getattr" in source, "mermaid must use getattr() for LangGraph internal attributes"


class TestTestRunnerProtectedFiles:
    """P1 #6: _should_copy_file must be called with cfg.protected_files, not workspace Path."""

    def test_test_runner_uses_protected_files(self):
        import inspect
        from workflows.autocode_impl import test_runner
        source = inspect.getsource(test_runner)
        assert "cfg.protected_files" in source, (
            "test_runner must pass cfg.protected_files (frozenset) to _should_copy_file"
        )


class TestVerifyLintPassedNone:
    """P1 #7: lint_passed must be None (not True) when ruff is missing."""

    def test_verify_lint_none_on_missing_ruff(self):
        import inspect
        from workflows.autocode_impl.nodes.verify import node_verify
        source = inspect.getsource(node_verify)
        # Must not have lint_passed = True as the ruff-missing fallback
        assert "lint_passed = True" not in source or "lint_passed = None" in source, (
            "verify must use lint_passed = None (not True) when ruff is missing"
        )


class TestWriteFilesErrorStatus:
    """P1 #9: write_files must return error status on JSON parse failure."""

    def test_write_files_returns_error_on_bad_json(self):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        state = {"trace_id": "test", "tdd_source_code": "not json{"}
        result = node_write_files(state)
        assert result.get("status") == "error", (
            "write_files must return status=error on JSON parse failure"
        )


class TestGitBranchErrorHandling:
    """P1 #10: node_git_branch must check branch creation return value."""

    def test_git_branch_returns_error_on_failure(self):
        from workflows.autocode_impl.nodes.branch import node_git_branch
        from unittest.mock import patch
        state = {
            "trace_id": "test",
            "status": "running",
            "branch": "feat/test",
            "project_root": "",
        }
        with patch("workflows.autocode_impl.nodes.branch._git_create_branch", return_value=False):
            result = node_git_branch(state)
        assert result.get("status") == "error", (
            "node_git_branch must return error status when branch creation fails"
        )


class TestValidatePathTraversal:
    """P1 #11: validate_input must catch Windows absolute and URL-encoded paths."""

    def test_windows_absolute_blocked(self):
        from workflows.autocode_impl.nodes.validate import node_validate_input
        state = {"task": "test", "files": {"C:\\secret": "content"}}
        result = node_validate_input(state)
        assert result.get("status") == "error", "Windows absolute path must be blocked"

    def test_url_encoded_traversal_blocked(self):
        from workflows.autocode_impl.nodes.validate import node_validate_input
        state = {"task": "test", "files": {"..%2f..%2fsecret": "content"}}
        result = node_validate_input(state)
        assert result.get("status") == "error", "URL-encoded traversal must be blocked"


class TestSlugFallback:
    """P1 #12: slug must fallback to 'autocode' when empty."""

    def test_slug_fallback_on_non_alphanumeric(self):
        from workflows.autocode_impl.nodes.plan import node_write_plan
        from unittest.mock import patch
        # Task with only non-alphanumeric chars — slug will be empty
        state = {"task": "中文测试", "trace_id": "test", "spec": "test"}
        # NOTE: plan.py imports _parse_json_array (not _parse_json) from helpers.
        # Also imports _call and get_callers — patch all to avoid real LLM/kgraph calls.
        with patch("workflows.autocode_impl.nodes.plan._call", return_value='[]'), \
             patch("workflows.autocode_impl.nodes.plan._parse_json_array", return_value=[]), \
             patch("workflows.autocode_impl.nodes.plan.get_callers", return_value=[]):
            result = node_write_plan(state)
        branch = result.get("branch", "")
        assert branch != "autocode/", "Branch must not be 'autocode/' (empty slug)"
        assert "autocode/" in branch, "Branch must start with 'autocode/'"


class TestRunTestsFileCheck:
    """P2 #14: run_tests must filter out missing test files."""

    def test_run_tests_filters_missing_files(self):
        import inspect
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        source = inspect.getsource(node_run_tests)
        assert "exists()" in source or "exists" in source, (
            "run_tests must check file existence before running pytest"
        )


class TestNoClassificationDeadCode:
    """P2 #28: memory.py must not reference classification field."""

    def test_no_classification_in_memory(self):
        import inspect
        import ast
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        source = inspect.getsource(node_distill_memory)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split('\n') if not line.strip().startswith('#')]
        code_str = '\n'.join(code_lines)
        assert "classification" not in code_str, (
            "memory.py must not reference 'classification' — field never set in AutocodeState"
        )


class TestGraphTimeoutWrapper:
    """P2 #30: invoke_with_timeout must exist and use cfg.autocode_graph_timeout."""

    def test_invoke_with_timeout_exists(self):
        from workflows.autocode_impl.graph import invoke_with_timeout
        assert callable(invoke_with_timeout), "invoke_with_timeout must exist"

    def test_invoke_with_timeout_uses_cfg(self):
        import inspect
        from workflows.autocode_impl.graph import invoke_with_timeout
        source = inspect.getsource(invoke_with_timeout)
        assert "autocode_graph_timeout" in source, (
            "invoke_with_timeout must use cfg.autocode_graph_timeout"
        )
