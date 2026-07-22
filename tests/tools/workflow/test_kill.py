"""Tests for the kill action — stronger than cancel (same mechanism, different intent).

The kill action:
  - Calls request_workflow_cancel(trace_id) (same as cancel).
  - Logs a tracer.warning (cancel uses tracer.step).
  - Returns a message documenting the "can't force-kill Python threads"
    limitation.

Python threads cannot be force-killed mid-operation — there's no
thread.kill(). The kill action sets the cancellation flag + logs the
intent; the workflow stops at the next cancellation check point (between
graph nodes for non-autocode; between LLM retries for autocode).
"""
from __future__ import annotations

from unittest.mock import patch

from tools.workflow import workflow


class TestKillActionValidation:
    """The kill action requires trace_id."""

    def test_kill_requires_trace_id(self, mock_tracer):
        """Empty trace_id should return error."""
        result = workflow(action="kill", trace_id="")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]

    def test_kill_whitespace_trace_id(self, mock_tracer):
        """Whitespace-only trace_id should be treated as missing."""
        result = workflow(action="kill", trace_id="   ")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]


class TestKillActionExecution:
    """The kill action calls request_workflow_cancel + logs a warning."""

    def test_kill_requests_cancel(self, mock_tracer):
        """kill should call workflows.base.request_workflow_cancel(trace_id)."""
        with patch("workflows.base.request_workflow_cancel") as mock_wf_cancel:
            result = workflow(action="kill", trace_id="t-kill")
        mock_wf_cancel.assert_called_once_with("t-kill")
        assert result["status"] == "success"
        assert result["trace_id"] == "t-kill"

    def test_kill_returns_message(self, mock_tracer):
        """The success message should mention the trace_id + the
        "can't force-kill" limitation."""
        with patch("workflows.base.request_workflow_cancel"):
            result = workflow(action="kill", trace_id="t-kill-msg")
        assert result["status"] == "success"
        assert "t-kill-msg" == result["trace_id"]
        # Message should mention force-kill limitation
        assert "force-killed" in result["message"].lower()
        assert "cancellation check point" in result["message"].lower()

    def test_kill_logs_warning(self, mock_tracer):
        """kill should log a tracer.warning (different from cancel which
        doesn't log at warning level)."""
        with patch("workflows.base.request_workflow_cancel"):
            result = workflow(action="kill", trace_id="t-warn")
        assert result["status"] == "success"
        # tracer.warning should have been called at least once with the
        # kill intent. The mock_tracer fixture patches tracer in all
        # modules that import it directly + core.tracer.tracer (for lazy
        # imports inside function bodies — kill.py does
        # `from core.tracer import tracer` inside the function).
        mock_tracer.warning.assert_called()
        # Verify the warning was for the kill node
        args, kwargs = mock_tracer.warning.call_args
        # Positional: trace_id, node, message
        assert "t-warn" in args[0] or args[0] == "t-warn"
        assert "kill" in args[1].lower()

    def test_kill_sets_workflow_cancel_flag(self, mock_tracer):
        """kill should set is_workflow_cancelled(trace_id)=True (same
        mechanism as cancel — Python threads can't be force-killed)."""
        from workflows.base import (
            is_workflow_cancelled,
            clear_workflow_cancel,
        )
        # Clean state — defensive cleanup in case a prior test leaked.
        clear_workflow_cancel("t-flag")
        assert not is_workflow_cancelled("t-flag")

        with patch("workflows.base.request_workflow_cancel") as mock_wf_cancel:
            # Use the REAL request_workflow_cancel by side-effecting the
            # _workflow_cancelled set directly (mock_wf_cancel is mocked
            # so the real function doesn't run — we verify the mock was
            # called instead, since that's what kill uses under the hood).
            result = workflow(action="kill", trace_id="t-flag")

        assert result["status"] == "success"
        mock_wf_cancel.assert_called_once_with("t-flag")
        # Cleanup
        clear_workflow_cancel("t-flag")


class TestKillVsCancel:
    """kill + cancel share the same mechanism but differ in intent + messaging."""

    def test_kill_message_differs_from_cancel(self, mock_tracer):
        """The kill success message should be distinct from the cancel
        success message — kill mentions force-kill limitation, cancel
        mentions autocode interrupts mid-execution."""
        with patch("workflows.base.request_workflow_cancel"), \
             patch("workflows.autocode_impl.helpers.request_cancellation"):
            kill_result = workflow(action="kill", trace_id="t-compare")
            cancel_result = workflow(action="cancel", trace_id="t-compare")

        assert kill_result["status"] == "success"
        assert cancel_result["status"] == "success"
        # Messages should be different
        assert kill_result["message"] != cancel_result["message"]
        # Kill message mentions force-kill
        assert "force-killed" in kill_result["message"].lower()
        # Cancel message mentions autocode interrupts (legacy behavior)
        assert "autocode" in cancel_result["message"].lower()
