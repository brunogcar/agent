"""Tests for the history action — queries the tracer for recent workflow runs."""
from __future__ import annotations

from unittest.mock import patch

from tools.workflow import workflow


class TestHistoryAction:
    """The history action queries tracer.recent and filters to workflow traces."""

    def test_history_returns_success(self, mock_tracer):
        mock_tracer.recent.return_value = []
        result = workflow(action="history", trace_id="t-hist")
        assert result["status"] == "success"

    def test_history_returns_runs_list(self, mock_tracer):
        """history should return a list of recent workflow runs."""
        mock_tracer.recent.return_value = [
            {
                "trace_id": "trace-1",
                "workflow": "research",
                "goal": "survey LLM agents",
                "status": "success",
                "elapsed": 12.5,
            },
            {
                "trace_id": "trace-2",
                "workflow": "autocode",
                "goal": "fix the bug",
                "status": "error",
                "elapsed": 5.0,
            },
        ]
        result = workflow(action="history", trace_id="t-hist")
        assert result["status"] == "success"
        assert len(result["runs"]) == 2
        assert result["count"] == 2
        assert result["runs"][0]["trace_id"] == "trace-1"
        assert result["runs"][0]["workflow"] == "research"

    def test_history_filters_non_workflow_traces(self, mock_tracer):
        """Non-workflow traces should be filtered out."""
        mock_tracer.recent.return_value = [
            {"trace_id": "wf-1", "workflow": "research", "goal": "..."},
            {"trace_id": "tool-1", "tool": "web", "goal": "search"},  # No workflow field
            {"trace_id": "wf-2", "category": "workflow", "goal": "..."},
            {"trace_id": "llm-1", "category": "llm", "goal": "chat"},  # Wrong category
        ]
        result = workflow(action="history", trace_id="t-filter")
        # Only wf-1 and wf-2 should be in the result
        assert result["count"] == 2
        trace_ids = [r["trace_id"] for r in result["runs"]]
        assert "wf-1" in trace_ids
        assert "wf-2" in trace_ids
        assert "tool-1" not in trace_ids
        assert "llm-1" not in trace_ids

    def test_history_truncates_goal(self, mock_tracer):
        """Goal should be truncated to 80 chars in the response."""
        long_goal = "x" * 200
        mock_tracer.recent.return_value = [
            {"trace_id": "t-long", "workflow": "research", "goal": long_goal},
        ]
        result = workflow(action="history", trace_id="t-hist")
        assert len(result["runs"][0]["goal"]) == 80

    def test_history_handles_empty_recent(self, mock_tracer):
        """Empty tracer.recent should return success with empty runs list."""
        mock_tracer.recent.return_value = []
        result = workflow(action="history", trace_id="t-empty")
        assert result["status"] == "success"
        assert result["runs"] == []
        assert result["count"] == 0

    def test_history_includes_trace_id(self, mock_tracer):
        mock_tracer.recent.return_value = []
        result = workflow(action="history", trace_id="t-hist-id")
        assert result["trace_id"] == "t-hist-id"

    def test_history_calls_tracer_recent_with_n_10(self, mock_tracer):
        """history should call tracer.recent(n=10)."""
        mock_tracer.recent.return_value = []
        workflow(action="history", trace_id="t-n")
        mock_tracer.recent.assert_called_once_with(n=10)


class TestHistoryActionErrors:
    """The history action handles tracer errors gracefully."""

    def test_history_handles_tracer_exception(self, mock_tracer):
        """If tracer.recent raises, history should return an error."""
        mock_tracer.recent.side_effect = RuntimeError("tracer db unavailable")
        result = workflow(action="history", trace_id="t-err")
        assert result["status"] == "error"
        assert "Failed to read tracer history" in result["error"]
        assert "tracer db unavailable" in result["error"]
