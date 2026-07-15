"""Tests for the autocode type handler validation.

Autocode takes git snapshots and modifies the filesystem, so it enforces
fail-fast parameter guards BEFORE any execution:
  - target_file is always required.
  - mode='fix_error' requires error_msg.
  - mode='add_feature' requires feature_desc.

Also tests the v1.0 pass-through params: files, git_diff, dry_run.
"""
from __future__ import annotations

from tools.workflow import workflow


class TestAutocodeValidation:
    """Autocode fail-fast parameter guards."""

    def test_missing_target_file(self, mock_tracer):
        """target_file is always required for autocode."""
        result = workflow(
            action="run", type="autocode",
            goal="fix the bug", trace_id="t1",
        )
        assert result["status"] == "error"
        assert "target_file is required" in result["error"]
        assert result["trace_id"] == "t1"
        assert result.get("workflow_type") == "autocode"

    def test_fix_error_missing_error_msg(self, mock_tracer):
        """mode='fix_error' requires error_msg."""
        result = workflow(
            action="run", type="autocode",
            goal="fix it", target_file="a.py",
            mode="fix_error", trace_id="t2",
        )
        assert result["status"] == "error"
        assert "error_msg is required" in result["error"]
        assert result.get("mode") == "fix_error"

    def test_add_feature_missing_feature_desc(self, mock_tracer):
        """mode='add_feature' requires feature_desc."""
        result = workflow(
            action="run", type="autocode",
            goal="add it", target_file="a.py",
            mode="add_feature", trace_id="t3",
        )
        assert result["status"] == "error"
        assert "feature_desc is required" in result["error"]
        assert result.get("mode") == "add_feature"

    def test_missing_goal(self, mock_tracer):
        """goal is required even for autocode."""
        result = workflow(
            action="run", type="autocode",
            goal="", target_file="a.py", trace_id="t4",
        )
        assert result["status"] == "error"
        assert "goal is required" in result["error"].lower()


class TestAutocodeExecution:
    """Autocode execution paths with valid params."""

    def test_successful_execution_improve_mode(self, mock_tracer, mock_run_workflow):
        """mode='improve' (default) requires only target_file."""
        result = workflow(
            action="run", type="autocode",
            goal="refactor auth", target_file="auth.py",
            trace_id="t5",
        )
        assert result["status"] == "success"
        assert result["trace_id"] == "t5"
        mock_run_workflow.assert_called_once()
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "autocode"
        assert kwargs["target_file"] == "auth.py"
        assert kwargs["mode"] == "improve"

    def test_fix_error_with_error_msg_executes(self, mock_tracer, mock_run_workflow):
        """mode='fix_error' with error_msg should execute."""
        result = workflow(
            action="run", type="autocode",
            goal="fix the bug", target_file="a.py",
            mode="fix_error", error_msg="KeyError: user",
            trace_id="t6",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["mode"] == "fix_error"
        assert kwargs["error_msg"] == "KeyError: user"

    def test_add_feature_with_feature_desc_executes(self, mock_tracer, mock_run_workflow):
        """mode='add_feature' with feature_desc should execute."""
        result = workflow(
            action="run", type="autocode",
            goal="add logging", target_file="a.py",
            mode="add_feature", feature_desc="Add structured logging",
            trace_id="t7",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["mode"] == "add_feature"
        assert kwargs["feature_desc"] == "Add structured logging"


class TestAutocodePassThroughParams:
    """v1.0 new params: files, git_diff, dry_run are forwarded to run_workflow."""

    def test_files_param_forwarded(self, mock_tracer, mock_run_workflow):
        """files (JSON dict of filename→content) should be forwarded."""
        files_json = '{"a.py": "print(1)"}'
        workflow(
            action="run", type="autocode",
            goal="refactor", target_file="a.py",
            files=files_json, trace_id="t-files",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs.get("files") == files_json

    def test_git_diff_param_forwarded(self, mock_tracer, mock_run_workflow):
        """git_diff=True should be forwarded."""
        workflow(
            action="run", type="autocode",
            goal="refactor from diff", target_file="a.py",
            git_diff=True, trace_id="t-gitdiff",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs.get("git_diff") is True

    def test_dry_run_param_forwarded(self, mock_tracer, mock_run_workflow):
        """dry_run=True should be forwarded."""
        workflow(
            action="run", type="autocode",
            goal="preflight check", target_file="a.py",
            dry_run=True, trace_id="t-dryrun",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs.get("dry_run") is True

    def test_no_pass_through_params_when_empty(self, mock_tracer, mock_run_workflow):
        """When files/git_diff/dry_run are empty/False, they should NOT be in kwargs.

        Matches the legacy behavior: empty params aren't forwarded to avoid
        confusing the workflow with empty defaults.
        """
        workflow(
            action="run", type="autocode",
            goal="refactor", target_file="a.py",
            trace_id="t-noextra",
        )
        _, kwargs = mock_run_workflow.call_args
        assert "files" not in kwargs
        assert "git_diff" not in kwargs
        assert "dry_run" not in kwargs


class TestAutocodeExecutionFailure:
    """Execution failures should return clean error dicts."""

    def test_execution_exception_returns_clean_error(self, mock_tracer, mock_run_workflow):
        """LangGraph crashes should be caught and returned as clean error dicts."""
        mock_run_workflow.side_effect = RuntimeError("LangGraph node crashed")
        result = workflow(
            action="run", type="autocode",
            goal="fix it", target_file="a.py", trace_id="t-err",
        )
        assert result["status"] == "error"
        assert "Workflow" in result["error"] or "failed" in result["error"].lower()
        assert result["trace_id"] == "t-err"
