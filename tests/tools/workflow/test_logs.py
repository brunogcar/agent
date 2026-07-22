"""Tests for the logs action — full step-by-step trace timeline + pagination."""
from __future__ import annotations

from unittest.mock import patch

from tools.workflow import workflow


class TestLogsAction:
    """The logs action calls read_trace(trace_id) and returns the full
    step-by-step timeline."""

    def test_logs_returns_full_trace(self, mock_tracer):
        """logs should return the trace's metadata + steps."""
        mock_trace = {
            "trace_id": "t-logs",
            "workflow": "research",
            "goal": "survey LLM agents",
            "status": "success",
            "started_at": "2026-07-25 10:00:00",
            "elapsed_s": 12.5,
            "result": "5 sources synthesized",
            "steps": [
                {"ts": 1, "event": "step", "node": "planner", "message": "planning"},
                {"ts": 2, "event": "step", "node": "search", "message": "searching"},
                {"ts": 3, "event": "step", "node": "synthesize", "message": "done"},
            ],
        }
        with patch("core.observability.reader.read_trace",
                   return_value=mock_trace) as mock_read:
            result = workflow(action="logs", trace_id="t-logs")

        assert result["status"] == "success"
        assert result["trace_id"] == "t-logs"
        assert result["workflow"] == "research"
        assert result["goal"] == "survey LLM agents"
        assert result["trace_status"] == "success"
        assert result["started_at"] == "2026-07-25 10:00:00"
        assert result["elapsed_s"] == 12.5
        assert result["result"] == "5 sources synthesized"
        assert len(result["steps"]) == 3
        assert result["steps"][0]["node"] == "planner"
        assert result["total_steps"] == 3
        assert result["offset"] == 0
        assert result["limit"] == 100
        assert result["trace_id_out"] == "t-logs"
        mock_read.assert_called_once_with("t-logs")

    def test_logs_requires_trace_id(self, mock_tracer):
        """Empty trace_id should return error."""
        result = workflow(action="logs", trace_id="")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]

    def test_logs_whitespace_trace_id(self, mock_tracer):
        """Whitespace-only trace_id should be treated as missing."""
        result = workflow(action="logs", trace_id="   ")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]


class TestLogsPagination:
    """The logs action supports limit + offset for paging through long
    traces."""

    def test_logs_pagination(self, mock_tracer):
        """150 steps, limit=100, offset=50 → 100 steps returned, total=150."""
        steps = [
            {"ts": i, "event": "step", "node": f"node_{i}", "message": f"step {i}"}
            for i in range(150)
        ]
        mock_trace = {
            "trace_id": "t-page",
            "workflow": "autocode",
            "goal": "test pagination",
            "status": "success",
            "started_at": "2026-07-25 10:00:00",
            "elapsed_s": 100.0,
            "result": "done",
            "steps": steps,
        }
        with patch("core.observability.reader.read_trace",
                   return_value=mock_trace):
            result = workflow(
                action="logs", trace_id="t-page",
                limit=100, offset=50,
            )

        assert result["status"] == "success"
        assert result["total_steps"] == 150
        assert result["offset"] == 50
        assert result["limit"] == 100
        assert len(result["steps"]) == 100
        # First step should be step 50 (index 50), last should be step 149
        assert result["steps"][0]["node"] == "node_50"
        assert result["steps"][-1]["node"] == "node_149"

    def test_logs_default_pagination(self, mock_tracer):
        """With no limit/offset, default limit=100, offset=0."""
        steps = [
            {"ts": i, "event": "step", "node": f"n{i}", "message": "m"}
            for i in range(50)
        ]
        mock_trace = {
            "trace_id": "t-def",
            "workflow": "research",
            "goal": "test",
            "status": "success",
            "started_at": "2026-07-25 10:00:00",
            "elapsed_s": 5.0,
            "result": "done",
            "steps": steps,
        }
        with patch("core.observability.reader.read_trace",
                   return_value=mock_trace):
            result = workflow(action="logs", trace_id="t-def")

        assert result["status"] == "success"
        assert result["limit"] == 100
        assert result["offset"] == 0
        assert len(result["steps"]) == 50  # only 50 exist
        assert result["total_steps"] == 50

    def test_logs_offset_beyond_end(self, mock_tracer):
        """If offset >= total_steps, return empty steps list (but still
        report total_steps)."""
        mock_trace = {
            "trace_id": "t-beyond",
            "workflow": "research",
            "goal": "test",
            "status": "success",
            "started_at": "2026-07-25 10:00:00",
            "elapsed_s": 1.0,
            "result": "done",
            "steps": [{"ts": i, "event": "step", "node": "n", "message": "m"}
                      for i in range(10)],
        }
        with patch("core.observability.reader.read_trace",
                   return_value=mock_trace):
            result = workflow(
                action="logs", trace_id="t-beyond",
                limit=100, offset=100,
            )

        assert result["status"] == "success"
        assert result["total_steps"] == 10
        assert result["steps"] == []


class TestLogsErrors:
    """The logs action handles missing traces + reader errors."""

    def test_logs_not_found(self, mock_tracer):
        """If read_trace returns None, return error."""
        with patch("core.observability.reader.read_trace",
                   return_value=None):
            result = workflow(action="logs", trace_id="t-missing")

        assert result["status"] == "error"
        assert "Trace not found" in result["error"]
        assert "t-missing" in result["error"]
        assert result["trace_id"] == "t-missing"
