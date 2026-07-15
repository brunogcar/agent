"""Tests for the run action dispatch — the first level of two-level dispatch.

The run action receives `type` and dispatches to TYPE_DISPATCH[type]["func"].
Each type handler validates its specific params and calls _execute_workflow().

This test file covers:
  - Dispatch to all 7 types (research, data, autocode, deep_research,
    understand, autoresearch, auto).
  - Type validation (empty, invalid, case insensitive).
  - Forwarding of type-specific params (code, target_file, project_root).
"""
from __future__ import annotations

from tools.workflow import workflow


class TestRunActionDispatch:
    """The run action dispatches to TYPE_DISPATCH based on `type`."""

    def test_run_dispatches_to_research(self, mock_tracer, mock_run_workflow):
        result = workflow(
            action="run", type="research",
            goal="survey LLM agents", trace_id="t-research",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "research"
        assert kwargs["goal"] == "survey LLM agents"

    def test_run_dispatches_to_data(self, mock_tracer, mock_run_workflow):
        result = workflow(
            action="run", type="data",
            goal="analyze sales.csv", code="print(df.head())", trace_id="t-data",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "data"
        assert kwargs.get("code") == "print(df.head())"

    def test_run_dispatches_to_data_without_code(self, mock_tracer, mock_run_workflow):
        """data workflow should still work without code param."""
        result = workflow(
            action="run", type="data",
            goal="analyze sales.csv", trace_id="t-data-nocode",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "data"
        assert "code" not in kwargs  # empty code shouldn't be forwarded

    def test_run_dispatches_to_autocode(self, mock_tracer, mock_run_workflow):
        result = workflow(
            action="run", type="autocode",
            goal="fix the bug", target_file="auth.py", trace_id="t-autocode",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "autocode"
        assert kwargs["target_file"] == "auth.py"

    def test_run_dispatches_to_deep_research(self, mock_tracer, mock_run_workflow):
        result = workflow(
            action="run", type="deep_research",
            goal="multi-faceted research", trace_id="t-deep",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "deep_research"

    def test_run_dispatches_to_understand(self, mock_tracer, mock_run_workflow):
        result = workflow(
            action="run", type="understand",
            goal="build knowledge graph", project_root="/repo", trace_id="t-understand",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "understand"
        assert kwargs["project_root"] == "/repo"

    def test_run_dispatches_to_autoresearch(self, mock_tracer, mock_run_workflow):
        result = workflow(
            action="run", type="autoresearch",
            goal="optimize the script", target_file="bench.py", trace_id="t-autoresearch",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "autoresearch"
        assert kwargs["target_file"] == "bench.py"

    def test_run_dispatches_to_auto(self, mock_tracer, mock_router, mock_run_workflow):
        """auto type uses the router — covered in detail in test_auto_routing.py."""
        result = workflow(
            action="run", type="auto",
            goal="research ai", trace_id="t-auto",
        )
        assert result["status"] == "success"
        mock_router.assert_called_once()


class TestRunActionValidation:
    """The run action validates `type` before dispatching."""

    def test_run_missing_type_returns_error(self, mock_tracer):
        result = workflow(action="run", goal="test", trace_id="t1")
        assert result["status"] == "error"
        assert "type is required" in result["error"].lower()
        assert "valid_types" in result

    def test_run_invalid_type_returns_error(self, mock_tracer):
        result = workflow(action="run", type="unknown_wf", goal="test", trace_id="t2")
        assert result["status"] == "error"
        assert "Invalid workflow type" in result["error"]
        assert "valid_types" in result

    def test_run_type_case_insensitive(self, mock_tracer, mock_run_workflow):
        """Type should be case-insensitive."""
        for type_str in ["RESEARCH", "Research", "research"]:
            mock_run_workflow.reset_mock()
            result = workflow(
                action="run", type=type_str,
                goal="test", trace_id=f"t-ci-{type_str}",
            )
            assert result["status"] == "success", f"{type_str} failed: {result}"


class TestRunActionParamForwarding:
    """Type-specific params are forwarded correctly through the run action."""

    def test_resume_param_forwarded(self, mock_tracer, mock_run_workflow):
        """resume=True should reach run_workflow."""
        workflow(
            action="run", type="research",
            goal="resume this", resume=True, trace_id="t-resume",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["resume"] is True

    def test_resume_defaults_to_false(self, mock_tracer, mock_run_workflow):
        """resume should default to False."""
        workflow(
            action="run", type="research",
            goal="fresh run", trace_id="t-noresume",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["resume"] is False

    def test_trace_id_in_run_workflow_kwargs(self, mock_tracer, mock_run_workflow):
        """trace_id should be forwarded to run_workflow."""
        workflow(
            action="run", type="research",
            goal="test", trace_id="t-fwd",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["trace_id"] == "t-fwd"
