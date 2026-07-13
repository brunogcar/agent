"""tests/workflows/base/test_dispatcher.py
Tests for run_workflow() — routing, checkpoint resume, autocode compat,
exception handling, unknown workflow type.
"""
from __future__ import annotations

from unittest.mock import patch


class TestRunWorkflowRouting:
    def test_unknown_workflow_returns_failed(self):
        from workflows.base import run_workflow
        result = run_workflow(workflow_type="unknown", goal="test", trace_id="t1")
        assert result["status"] == "failed"
        assert "Unknown workflow type" in result["error"]

    def test_unknown_workflow_error_lists_all_types(self):
        from workflows.base import run_workflow
        result = run_workflow(workflow_type="bad", goal="test", trace_id="t2")
        for wf in ["research", "data", "autocode", "deep_research", "understand", "autoresearch"]:
            assert wf in result["error"], f"Error message must list {wf}"

    def test_workflow_type_case_insensitive(self, mocker):
        """workflow_type should be lowercased before routing."""
        from workflows.base import run_workflow
        mock_graph = mocker.patch("workflows.research.build_research_graph")
        mock_compiled = mocker.MagicMock()
        mock_compiled.invoke.return_value = {"status": "success"}
        mock_graph.return_value = mock_compiled
        result = run_workflow(workflow_type="RESEARCH", goal="test", trace_id="t3")
        mock_graph.assert_called_once()


class TestRunWorkflowAutocodeCompat:
    def test_autocode_converts_goal_to_task(self, mocker):
        """run_workflow must set task=goal for autocode."""
        from workflows.base import run_workflow
        mock_invoke = mocker.patch("workflows.autocode_impl.graph.invoke_with_timeout")
        mock_invoke.return_value = {"status": "success"}
        run_workflow(workflow_type="autocode", goal="fix the bug", trace_id="t4")
        state_passed = mock_invoke.call_args[0][0]
        assert state_passed["task"] == "fix the bug"
        assert state_passed["goal"] == "fix the bug"


class TestRunWorkflowCheckpoint:
    def test_resume_restores_checkpoint(self, mocker):
        """resume=True must restore from checkpoint journal."""
        from workflows.base import run_workflow
        mocker.patch(
            "core.observability.checkpoint.get_latest",
            return_value={"_checkpoint_version": 1, "goal": "original", "memory_context": "ctx"},
        )
        mock_graph = mocker.patch("workflows.research.build_research_graph")
        mock_compiled = mocker.MagicMock()
        mock_compiled.invoke.return_value = {"status": "success"}
        mock_graph.return_value = mock_compiled
        run_workflow(workflow_type="research", goal="NEW goal", trace_id="t5", resume=True)
        state_passed = mock_compiled.invoke.call_args[0][0]
        assert state_passed["goal"] == "original", (
            "Resume must keep the checkpoint's original goal — was clobbering with the new goal"
        )

    def test_resume_version_mismatch_starts_fresh(self, mocker):
        from workflows.base import run_workflow
        mocker.patch(
            "core.observability.checkpoint.get_latest",
            return_value={"_checkpoint_version": 99, "goal": "old"},
        )
        mock_graph = mocker.patch("workflows.research.build_research_graph")
        mock_compiled = mocker.MagicMock()
        mock_compiled.invoke.return_value = {"status": "success"}
        mock_graph.return_value = mock_compiled
        run_workflow(workflow_type="research", goal="new", trace_id="t6", resume=True)
        state_passed = mock_compiled.invoke.call_args[0][0]
        assert state_passed["goal"] == "new", "Version mismatch should start fresh with the new goal"

    def test_resume_no_checkpoint_starts_fresh(self, mocker):
        from workflows.base import run_workflow
        mocker.patch("core.observability.checkpoint.get_latest", return_value=None)
        mock_graph = mocker.patch("workflows.research.build_research_graph")
        mock_compiled = mocker.MagicMock()
        mock_compiled.invoke.return_value = {"status": "success"}
        mock_graph.return_value = mock_compiled
        run_workflow(workflow_type="research", goal="test", trace_id="t7", resume=True)
        mock_graph.assert_called_once()


class TestRunWorkflowExceptionHandling:
    def test_crash_saves_checkpoint(self, mocker):
        """[v1.2 #2] Exception handler must save a checkpoint before returning."""
        from workflows.base import run_workflow
        mock_graph = mocker.patch("workflows.research.build_research_graph")
        mock_graph.return_value.invoke.side_effect = RuntimeError("graph crashed")
        mock_save = mocker.patch("core.observability.checkpoint.save_checkpoint")
        result = run_workflow(workflow_type="research", goal="test", trace_id="t8")
        assert result["status"] == "failed"
        assert "graph crashed" in result["error"]
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][2]
        assert saved_state["status"] == "failed"
        assert "graph crashed" in saved_state["error"]

    def test_crash_returns_clean_failure_dict(self, mocker):
        from workflows.base import run_workflow
        mock_graph = mocker.patch("workflows.research.build_research_graph")
        mock_graph.return_value.invoke.side_effect = RuntimeError("boom")
        result = run_workflow(workflow_type="research", goal="test", trace_id="t9")
        assert result["status"] == "failed"
        assert result["result"] == ""
        assert result["artifacts"] == []
        assert "RuntimeError" in result["error"]


class TestRunWorkflowInputValidation:
    """v1.3.1 (P2-1): Input validation — fail fast before trace creation."""

    def test_empty_workflow_type_fails_fast(self):
        """Empty workflow_type returns error before creating trace or building state."""
        from workflows.base import run_workflow
        result = run_workflow(workflow_type="", goal="test", trace_id="t10")
        assert result["status"] == "failed"
        assert "workflow_type is required" in result["error"]

    def test_empty_goal_fails_fast(self):
        """Empty goal returns error before creating trace."""
        from workflows.base import run_workflow
        result = run_workflow(workflow_type="research", goal="", trace_id="t11")
        assert result["status"] == "failed"
        assert "goal is required" in result["error"]

    def test_whitespace_goal_fails_fast(self):
        """Whitespace-only goal returns error."""
        from workflows.base import run_workflow
        result = run_workflow(workflow_type="research", goal="   ", trace_id="t12")
        assert result["status"] == "failed"
        assert "goal is required" in result["error"]

    def test_empty_workflow_type_does_not_create_trace(self, mocker):
        """Validation should fire before tracer.new_trace is called."""
        from workflows.base import run_workflow
        mock_new_trace = mocker.patch("core.tracer.tracer.new_trace")
        result = run_workflow(workflow_type="", goal="test")
        assert result["status"] == "failed"
        mock_new_trace.assert_not_called()
