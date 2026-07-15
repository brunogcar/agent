"""Tests for general validation in the workflow facade and run action.

Covers:
  - Empty action → clear error
  - Unknown action → error listing valid actions
  - Empty goal for action='run' → error
  - Empty type for action='run' → error
  - Invalid type for action='run' → error listing valid types
  - trace_id auto-generation when not provided
  - Case insensitivity of action
"""
from __future__ import annotations

from tools.workflow import workflow


class TestActionValidation:
    """Facade-level action validation."""

    def test_empty_action_returns_error(self):
        """Empty action should return clear 'action is required' error."""
        result = workflow(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"].lower()

    def test_unknown_action_returns_error(self):
        """Unknown action should list valid actions."""
        result = workflow(action="nonexistent", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        assert "run" in result["error"]
        assert "list" in result["error"]
        assert "status" in result["error"]
        assert "cancel" in result["error"]
        assert "history" in result["error"]

    def test_action_case_insensitive(self, mock_tracer, mock_run_workflow):
        """Action should be case-insensitive (RUN / Run / run all dispatch)."""
        result_upper = workflow(action="RUN", type="research", goal="test", trace_id="t1")
        assert result_upper["status"] == "success", f"RUN failed: {result_upper}"

        result_mixed = workflow(action="Run", type="research", goal="test", trace_id="t2")
        assert result_mixed["status"] == "success", f"Run failed: {result_mixed}"

        result_lower = workflow(action="run", type="research", goal="test", trace_id="t3")
        assert result_lower["status"] == "success", f"run failed: {result_lower}"

    def test_trace_id_in_error_responses(self):
        """trace_id should be present in error responses from the facade."""
        result = workflow(action="nonexistent", trace_id="trace-err-1")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-err-1"

        result = workflow(action="", trace_id="trace-err-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-err-2"


class TestRunActionTypeValidation:
    """The run action validates `type` before dispatching."""

    def test_empty_type_for_run_returns_error(self, mock_tracer):
        """Empty type for action='run' should return error."""
        result = workflow(action="run", goal="test", trace_id="t1")
        assert result["status"] == "error"
        assert "type is required" in result["error"].lower()
        assert result["trace_id"] == "t1"
        assert "valid_types" in result

    def test_invalid_type_for_run_returns_error(self, mock_tracer):
        """Invalid type should list valid types."""
        result = workflow(action="run", type="coding", goal="test", trace_id="t2")
        assert result["status"] == "error"
        assert "Invalid workflow type" in result["error"]
        assert "coding" in result["error"]
        assert result["trace_id"] == "t2"
        assert "valid_types" in result

    def test_type_case_insensitive(self, mock_tracer, mock_run_workflow):
        """Type should be case-insensitive (RESEARCH / Research / research)."""
        result_upper = workflow(action="run", type="RESEARCH", goal="test", trace_id="t1")
        assert result_upper["status"] == "success", f"RESEARCH failed: {result_upper}"

        result_mixed = workflow(action="run", type="Research", goal="test", trace_id="t2")
        assert result_mixed["status"] == "success", f"Research failed: {result_mixed}"


class TestRunActionGoalValidation:
    """The run action + type handlers validate `goal`."""

    def test_empty_goal_for_run_returns_error(self, mock_tracer):
        """Empty goal should return error from the type handler."""
        result = workflow(action="run", type="research", goal="", trace_id="t1")
        assert result["status"] == "error"
        assert "goal is required" in result["error"].lower()
        assert result["trace_id"] == "t1"

    def test_whitespace_goal_for_run_returns_error(self, mock_tracer):
        """Whitespace-only goal should be treated as empty."""
        result = workflow(action="run", type="research", goal="   ", trace_id="t2")
        assert result["status"] == "error"
        assert "goal is required" in result["error"].lower()


class TestTraceIdAutoGeneration:
    """trace_id is auto-generated when not provided."""

    def test_trace_id_generated_when_missing(self, mock_tracer, mock_run_workflow):
        """If trace_id is empty, a new one is generated via tracer.new_trace."""
        mock_tracer.new_trace.return_value = "generated-trace-id"
        result = workflow(action="run", type="research", goal="test")
        assert result["trace_id"] == "generated-trace-id"
        mock_tracer.new_trace.assert_called_once()

    def test_trace_id_preserved_when_provided(self, mock_tracer, mock_run_workflow):
        """If trace_id is provided, it should be used as-is."""
        result = workflow(action="run", type="research", goal="test", trace_id="caller-trace")
        assert result["trace_id"] == "caller-trace"
        mock_tracer.new_trace.assert_not_called()
