"""Tests for the status action — checkpoint + tracer summary lookup."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.workflow import workflow


class TestStatusActionValidation:
    """The status action requires trace_id."""

    def test_status_requires_trace_id(self, mock_tracer):
        """Empty trace_id should return error."""
        result = workflow(action="status", trace_id="")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]

    def test_status_whitespace_trace_id(self, mock_tracer):
        """Whitespace-only trace_id should be treated as missing."""
        result = workflow(action="status", trace_id="   ")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]


class TestStatusActionCheckpoint:
    """The status action reads from the checkpoint journal."""

    def test_status_with_checkpoint(self, mock_tracer, mock_checkpoint):
        """When a checkpoint exists, status should report it."""
        mock_checkpoint.return_value = {
            "_checkpoint_node": "planner",
            "status": "running",
        }
        result = workflow(action="status", trace_id="t-cp", )
        assert result["status"] == "success"
        assert result["trace_id"] == "t-cp"
        assert result["checkpoint"] is True
        assert result["checkpoint_node"] == "planner"
        assert result["checkpoint_status"] == "running"

    def test_status_without_checkpoint(self, mock_tracer, mock_checkpoint):
        """When no checkpoint exists, status should report checkpoint=False."""
        mock_checkpoint.return_value = None
        result = workflow(action="status", trace_id="t-nocp")
        assert result["status"] == "success"
        assert result["checkpoint"] is False
        assert result["checkpoint_node"] == ""
        assert result["checkpoint_status"] == ""


class TestStatusActionTracerSummary:
    """The status action reads tracer.summary for the trace_id."""

    def test_status_includes_tracer_summary(self, mock_tracer):
        """tracer.summary should be called and its result included."""
        mock_tracer.summary.return_value = {"steps": 5, "last_step": "planner"}
        result = workflow(action="status", trace_id="t-summary")
        assert result["status"] == "success"
        assert result["tracer_summary"] == {"steps": 5, "last_step": "planner"}
        mock_tracer.summary.assert_called_once_with("t-summary")

    def test_status_handles_tracer_error(self, mock_tracer):
        """If tracer.summary raises, status should still return success with None summary."""
        mock_tracer.summary.side_effect = RuntimeError("tracer unavailable")
        result = workflow(action="status", trace_id="t-tracererr")
        assert result["status"] == "success"
        assert result["tracer_summary"] is None


class TestStatusActionCheckpointError:
    """The status action handles checkpoint module errors gracefully."""

    def test_status_handles_checkpoint_import_error(self, mock_tracer):
        """If checkpoint module can't be imported, status should still return success."""
        with patch("core.observability.checkpoint.get_latest", side_effect=ImportError("no module")):
            result = workflow(action="status", trace_id="t-importerr")
        assert result["status"] == "success"
        assert result["checkpoint"] is False

    def test_status_handles_checkpoint_runtime_error(self, mock_tracer):
        """If checkpoint.get_latest raises at runtime, status should still return success."""
        with patch("core.observability.checkpoint.get_latest", side_effect=RuntimeError("db error")):
            result = workflow(action="status", trace_id="t-rterr")
        assert result["status"] == "success"
        assert result["checkpoint"] is False
