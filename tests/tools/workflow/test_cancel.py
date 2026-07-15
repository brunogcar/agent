"""Tests for the cancel action — sets the autocode cancellation flag."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.workflow import workflow


class TestCancelActionValidation:
    """The cancel action requires trace_id."""

    def test_cancel_requires_trace_id(self, mock_tracer):
        """Empty trace_id should return error."""
        result = workflow(action="cancel", trace_id="")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]

    def test_cancel_whitespace_trace_id(self, mock_tracer):
        """Whitespace-only trace_id should be treated as missing."""
        result = workflow(action="cancel", trace_id="   ")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]


class TestCancelActionExecution:
    """The cancel action calls request_cancellation on the autocode helpers."""

    def test_cancel_calls_request_cancellation(self, mock_tracer):
        """cancel should call workflows.autocode_impl.helpers.request_cancellation."""
        with patch("workflows.autocode_impl.helpers.request_cancellation") as mock_cancel:
            result = workflow(action="cancel", trace_id="t-cancel")
            mock_cancel.assert_called_once()
        assert result["status"] == "success"
        assert result["trace_id"] == "t-cancel"

    def test_cancel_returns_success_message(self, mock_tracer):
        """The success message should mention the trace_id and autocode limitation."""
        with patch("workflows.autocode_impl.helpers.request_cancellation"):
            result = workflow(action="cancel", trace_id="t-cancel-msg")
        assert result["status"] == "success"
        assert "t-cancel-msg" in result["message"]
        assert "autocode" in result["message"].lower()

    def test_cancel_handles_request_cancellation_exception(self, mock_tracer):
        """If request_cancellation raises, status should be error."""
        with patch("workflows.autocode_impl.helpers.request_cancellation",
                   side_effect=RuntimeError("flag write failed")):
            result = workflow(action="cancel", trace_id="t-cancel-err")
        assert result["status"] == "error"
        assert "Failed to cancel" in result["error"]
        assert "flag write failed" in result["error"]


class TestCancelActionMissingAutocode:
    """The cancel action handles missing autocode module gracefully."""

    def test_cancel_handles_import_error(self, mock_tracer):
        """If autocode helpers module can't be imported, status should still be success.

        The cancel action catches ImportError and returns a success message
        noting that no cancellation mechanism is available.
        """
        with patch("workflows.autocode_impl.helpers.request_cancellation",
                   side_effect=ImportError("module not installed")):
            result = workflow(action="cancel", trace_id="t-no-autocode")
        assert result["status"] == "success"
        assert "t-no-autocode" in result["message"]
        assert "no cancellation mechanism" in result["message"].lower()
