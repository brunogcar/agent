"""Tests for the cancel action — sets BOTH cancellation flags.

v1.1-p1 (workflow-v1.1-p1): The cancel action now sets:
  1. request_workflow_cancel(trace_id) — general-purpose, checked by
     run_workflow() after dispatch returns (all workflows).
  2. request_cancellation() — autocode-specific, checked by _call()
     between retries (autocode only — mid-execution interrupt).

For non-autocode workflows, the cancel takes effect after the current step
completes (graph.invoke is blocking, can't be interrupted). For autocode,
the cancel interrupts mid-execution (e.g. wakes up LLM backoff sleeps).
"""
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
    """The cancel action calls BOTH request_cancellation AND
    request_workflow_cancel(trace_id)."""

    def test_cancel_calls_request_cancellation(self, mock_tracer):
        """cancel should call workflows.autocode_impl.helpers.request_cancellation
        (autocode-specific mid-execution interrupt)."""
        with patch("workflows.autocode_impl.helpers.request_cancellation") as mock_cancel, \
             patch("workflows.base.request_workflow_cancel"):
            result = workflow(action="cancel", trace_id="t-cancel")
        mock_cancel.assert_called_once()
        assert result["status"] == "success"
        assert result["trace_id"] == "t-cancel"

    def test_cancel_calls_request_workflow_cancel(self, mock_tracer):
        """cancel should call workflows.base.request_workflow_cancel(trace_id)
        (general-purpose flag for ALL workflows)."""
        with patch("workflows.autocode_impl.helpers.request_cancellation"), \
             patch("workflows.base.request_workflow_cancel") as mock_wf_cancel:
            result = workflow(action="cancel", trace_id="t-cancel-wf")
        mock_wf_cancel.assert_called_once_with("t-cancel-wf")
        assert result["status"] == "success"
        assert result["trace_id"] == "t-cancel-wf"

    def test_cancel_returns_success_message(self, mock_tracer):
        """The success message should mention the trace_id and the
        cancellation semantics (autocode interrupts mid-execution)."""
        with patch("workflows.autocode_impl.helpers.request_cancellation"), \
             patch("workflows.base.request_workflow_cancel"):
            result = workflow(action="cancel", trace_id="t-cancel-msg")
        assert result["status"] == "success"
        assert "t-cancel-msg" in result["message"]
        # Message should still mention autocode (interrupts mid-execution)
        assert "autocode" in result["message"].lower()
        # autocode_cancelled flag should be True when autocode is available
        assert result.get("autocode_cancelled") is True

    def test_cancel_handles_request_cancellation_exception(self, mock_tracer):
        """If request_cancellation raises, status should be error."""
        with patch("workflows.autocode_impl.helpers.request_cancellation",
                   side_effect=RuntimeError("flag write failed")), \
             patch("workflows.base.request_workflow_cancel"):
            result = workflow(action="cancel", trace_id="t-cancel-err")
        assert result["status"] == "error"
        assert "Failed to cancel" in result["error"]
        assert "flag write failed" in result["error"]


class TestCancelActionMissingAutocode:
    """The cancel action handles missing autocode module gracefully — the
    general-purpose flag is still set, so non-autocode workflows can still
    be cancelled."""

    def test_cancel_handles_import_error(self, mock_tracer):
        """If autocode helpers module can't be imported, status should still be success.

        With the new flow, the general-purpose workflow cancellation flag
        (request_workflow_cancel) is still set, so non-autocode workflows
        can still be cancelled. Only the autocode-specific mid-execution
        interrupt is unavailable.
        """
        with patch("workflows.autocode_impl.helpers.request_cancellation",
                   side_effect=ImportError("module not installed")), \
             patch("workflows.base.request_workflow_cancel") as mock_wf_cancel:
            result = workflow(action="cancel", trace_id="t-no-autocode")
        assert result["status"] == "success"
        assert "t-no-autocode" in result["message"]
        # request_workflow_cancel was still called even though autocode is missing
        mock_wf_cancel.assert_called_once_with("t-no-autocode")
        # autocode_cancelled flag reflects that autocode wasn't available
        assert result.get("autocode_cancelled") is False


class TestCancelActionWorkflowFlag:
    """v1.1-p1: New tests for the general-purpose workflow cancellation flag."""

    def test_cancel_sets_workflow_cancel_flag(self, mock_tracer):
        """cancel should call request_workflow_cancel with the trace_id.

        Uses the REAL request_workflow_cancel (not a mock) so we can verify
        is_workflow_cancelled(trace_id) returns True afterward.
        """
        from workflows.base import (
            request_workflow_cancel,
            is_workflow_cancelled,
            clear_workflow_cancel,
            _workflow_cancelled,
        )
        # Clean state — defensive cleanup in case a prior test leaked.
        clear_workflow_cancel("t-wf-flag")
        assert not is_workflow_cancelled("t-wf-flag")

        with patch("workflows.autocode_impl.helpers.request_cancellation"):
            result = workflow(action="cancel", trace_id="t-wf-flag")

        assert result["status"] == "success"
        assert is_workflow_cancelled("t-wf-flag")
        # Cleanup
        clear_workflow_cancel("t-wf-flag")

    def test_cancel_non_autocode_workflow(self, mock_tracer):
        """Cancelling a non-autocode workflow should set
        is_workflow_cancelled(trace_id)=True. The flag persists until
        run_workflow() observes it (post-dispatch) and calls clear_workflow_cancel.
        """
        from workflows.base import (
            is_workflow_cancelled,
            clear_workflow_cancel,
        )
        # Clean state
        clear_workflow_cancel("t-non-auto")
        assert not is_workflow_cancelled("t-non-auto")

        with patch("workflows.autocode_impl.helpers.request_cancellation"):
            result = workflow(action="cancel", trace_id="t-non-auto")

        assert result["status"] == "success"
        # The general-purpose flag IS set even for non-autocode workflows
        assert is_workflow_cancelled("t-non-auto")
        # Cleanup
        clear_workflow_cancel("t-non-auto")

    def test_cancel_idempotent(self, mock_tracer):
        """Calling cancel twice on the same trace_id is a no-op for the
        general-purpose flag (set semantics)."""
        from workflows.base import clear_workflow_cancel, _workflow_cancelled
        clear_workflow_cancel("t-idempotent")
        with patch("workflows.autocode_impl.helpers.request_cancellation"):
            workflow(action="cancel", trace_id="t-idempotent")
            workflow(action="cancel", trace_id="t-idempotent")
        # Still in the set (set semantics — duplicate adds are no-ops)
        assert "t-idempotent" in _workflow_cancelled
        clear_workflow_cancel("t-idempotent")
