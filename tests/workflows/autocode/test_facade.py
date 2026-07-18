"""tests/workflows/autocode/test_facade.py
Facade contract tests — verify the public API works (import + run_workflow).
Also includes #44 (structured artifacts), #46 (git-diff input), and #47
(dry-run guards on the facade level).

[v1.2] Removed run_autocode_agent tests — the shim was deleted (roadmap #34).
Callers now use run_workflow("autocode") directly. _shape_artifacts is still
tested as a public utility.
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock


# ─── Facade imports ─────────────────────────────────────────────────────────

class TestFacadeImports:
    def test_facade_imports_cleanly(self):
        """import workflows.autocode must succeed (was broken for 2 versions)."""
        import workflows.autocode as facade
        assert hasattr(facade, "build_graph")
        assert hasattr(facade, "get_graph")
        assert hasattr(facade, "WORKFLOW_METADATA")

    def test_all_exports_resolve(self):
        import workflows.autocode as facade
        for name in facade.__all__:
            assert hasattr(facade, name), f"__all__ lists {name!r} but not on module"

    def test_no_dead_imports(self):
        """v1.1: 4 dead imports removed (AGENT_ROOT, route_after_brainstorm/debug, _git_snapshot)."""
        import workflows.autocode as facade
        assert not hasattr(facade, "AGENT_ROOT")
        assert not hasattr(facade, "route_after_brainstorm")
        assert not hasattr(facade, "route_after_debug")
        assert not hasattr(facade, "_git_snapshot")

    def test_run_autocode_agent_shim_removed(self):
        """[v1.2 roadmap #34] run_autocode_agent shim was removed."""
        import workflows.autocode as facade
        assert not hasattr(facade, "run_autocode_agent")
        assert "run_autocode_agent" not in facade.__all__


# ─── run_workflow integration ──────────────────────────────────────────────

class TestRunWorkflowAutocode:
    def test_run_workflow_reaches_graph(self):
        """run_workflow('autocode') must call invoke_with_timeout, not crash."""
        from workflows.base import run_workflow
        with patch("workflows.autocode_impl.graph.invoke_with_timeout") as mock_invoke:
            mock_invoke.return_value = {"status": "success", "result": "done"}
            result = run_workflow(
                workflow_type="autocode", goal="test task", task="test task",
                files={}, trace_id="test-facade-1",
            )
            assert result["status"] == "success"
            assert mock_invoke.called

    def test_kwargs_pass_through(self):
        from workflows.base import run_workflow
        with patch("workflows.autocode_impl.graph.invoke_with_timeout") as mock_invoke:
            mock_invoke.return_value = {"status": "success"}
            run_workflow(
                workflow_type="autocode", goal="add retry", task="add retry",
                files={"tools/web.py": "content"}, mode="feature",
                target_file="tools/web.py", dry_run=True, trace_id="t1",
            )
            call_state = mock_invoke.call_args[0][0]
            assert call_state.get("files") == {"tools/web.py": "content"}
            assert call_state.get("mode") == "feature"
            assert call_state.get("dry_run") is True


# ─── #44: Structured artifacts ──────────────────────────────────────────────

class TestStructuredArtifacts:
    def test_shape_artifacts_extracts_fields(self):
        from workflows.autocode import _shape_artifacts
        # [v3.0] _shape_artifacts reads via accessors — populate the sub-states.
        final_state = {
            "vcs": {"commit_sha": "abc123", "branch": "fix-bug"},
            "files_state": {"modified_files": ["a.py", "b.py"]},
            "test_results": {"success": True},
            "tdd": {"status": "passed", "iteration": 2},
            "verify": {"passed": True},
        }
        art = _shape_artifacts(final_state)
        assert art["commit_sha"] == "abc123"
        assert art["branch_name"] == "fix-bug"
        assert art["modified_files"] == ["a.py", "b.py"]
        assert art["tdd_status"] == "passed"

    def test_shape_artifacts_defaults_on_empty(self):
        from workflows.autocode import _shape_artifacts
        art = _shape_artifacts({})
        assert art["commit_sha"] == ""
        assert art["modified_files"] == []
        assert art["verification_passed"] is False


# ─── #46: Multi-file git-diff input ─────────────────────────────────────────

class TestGitDiffInput:
    def test_no_git_diff_returns_files_as_is(self):
        from workflows.autocode import _resolve_files_input
        files = {"a.py": "content", "b.py": "more"}
        assert _resolve_files_input(files, git_diff=False) == files

    def test_git_diff_false_strips_all_changed_key(self):
        from workflows.autocode import _resolve_files_input
        assert _resolve_files_input({"all changed": "", "a.py": "content"}, git_diff=False) == {"a.py": "content"}

    def test_git_diff_true_resolves_changed_files(self, tmp_path, mocker):
        from workflows.autocode import _resolve_files_input
        (tmp_path / "changed.py").write_text("print('hello')", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "changed.py\n"
        mocker.patch("subprocess.run", return_value=mock_result)
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _resolve_files_input({"all changed": ""}, git_diff=True)
        finally:
            os.chdir(old_cwd)
        assert "changed.py" in result
        assert result["changed.py"] == "print('hello')"

    def test_git_diff_merges_explicit_files(self, tmp_path, mocker):
        from workflows.autocode import _resolve_files_input
        (tmp_path / "diff_file.py").write_text("content", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff_file.py\n"
        mocker.patch("subprocess.run", return_value=mock_result)
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _resolve_files_input(
                {"all changed": "", "explicit.py": "explicit content"}, git_diff=True,
            )
        finally:
            os.chdir(old_cwd)
        assert "diff_file.py" in result
        assert "explicit.py" in result
        assert result["explicit.py"] == "explicit content"

    def test_git_diff_failure_returns_empty(self, mocker):
        from workflows.autocode import _resolve_files_input
        mocker.patch("subprocess.run", side_effect=Exception("git not found"))
        assert _resolve_files_input({"all changed": ""}, git_diff=True) == {}


# ─── #47: Dry-run guards ────────────────────────────────────────────────────

class TestDryRunGuards:
    def test_write_files_skips_on_dry_run(self):
        from workflows.autocode_impl.nodes.write_files import node_write_files
        # [v3.0] tdd_source_code lives ONLY in the tdd sub-state.
        state = {"dry_run": True, "tdd": {"source_code": '{"patches": []}'}, "trace_id": "t1"}
        result = node_write_files(state)
        assert result["status"] == "dry_run"
        # [v3.0] modified_files lives ONLY in the files sub-state.
        assert result["files_state"]["modified_files"] == []

    def test_commit_skips_on_dry_run(self):
        from workflows.autocode_impl.nodes.commit import node_commit
        with patch("workflows.autocode_impl.git_ops._git_commit") as mock_git:
            # [v3.0] verify + vcs sub-states are the PRIMARY storage.
            state = {"dry_run": True,
                     "plan_state": {"plan": [], "current_step": 0, "spec": "", "brainstorm_notes": "", "plan_accepted": False},
                     "task": "test", "task_type": "feature", "trace_id": "t1",
                     "verify": {"passed": True, "notes": "", "report": ""},
                     "vcs": {"commit_sha": "", "branch": "", "pushed": False, "pr_number": 0, "pr_url": ""}}
            result = node_commit(state)
        assert result["status"] == "dry_run"
        # [v3.0] commit_sha lives ONLY in the vcs sub-state now.
        assert result["vcs"]["commit_sha"] == "(dry-run)"
        assert not mock_git.called

    def test_branch_skips_on_dry_run(self):
        from workflows.autocode_impl.nodes.branch import node_git_branch
        with patch("workflows.autocode_impl.git_ops._git_create_branch") as mock_branch:
            # [v3.0] Include vcs sub-state for consistency (dry_run exits early,
            # but the state should still be well-formed).
            state = {"dry_run": True, "trace_id": "t1",
                     "vcs": {"branch": "feat-x", "commit_sha": "", "pushed": False, "pr_number": 0, "pr_url": ""}}
            result = node_git_branch(state)
        assert result == {}
        assert not mock_branch.called

    def test_commit_proceeds_without_dry_run(self, mocker):
        from workflows.autocode_impl.nodes.commit import node_commit
        mock_git_commit = mocker.patch(
            "workflows.autocode_impl.nodes.commit._git_commit", return_value="abc123"
        )
        # [v3.0] Include sub-states so accessors find the values (sub-state only).
        state = {"dry_run": False,
                 "plan_state": {"plan": [], "current_step": 0, "spec": "", "brainstorm_notes": "", "plan_accepted": False},
                 "task": "test", "task_type": "feature", "trace_id": "t1",
                 "verify": {"passed": True, "notes": "", "report": ""},
                 "vcs": {"commit_sha": "", "branch": "", "pushed": False, "pr_number": 0, "pr_url": ""}}
        result = node_commit(state)
        assert mock_git_commit.called
        # [v3.0] commit_sha lives ONLY in the vcs sub-state now.
        assert result["vcs"]["commit_sha"] == "abc123"


# ─── Distill memory non-fatal ───────────────────────────────────────────────

class TestDistillMemoryNonFatal:
    """v1.1: distill_memory failure must not fail the workflow."""

    def test_distill_memory_uses_warning_not_error(self):
        import inspect, ast
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        source = inspect.getsource(node_distill_memory)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant,))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split("\n") if not line.strip().startswith("#")]
        code_str = "\n".join(code_lines)
        assert "tracer.warning" in code_str
        assert "tracer.error(" not in code_str
