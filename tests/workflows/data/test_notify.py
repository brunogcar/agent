"""tests/workflows/data/test_notify.py
Tests for node_notify — notification + node_done, with graceful notify failure.
"""
from __future__ import annotations

from unittest.mock import patch

from workflows.data_impl.nodes.notify import node_notify


class TestNodeNotify:
    def test_calls_notify_with_action_send(self, base_state):
        base_state["result"] = "Analysis complete: top months are Jan, Mar"
        with patch("tools.notify.notify") as mock_notify:
            out = node_notify(base_state)
        assert mock_notify.called
        _, kwargs = mock_notify.call_args
        assert kwargs.get("action") == "send"
        assert "Data analysis complete" == kwargs.get("title")
        # node_done marks the workflow successful.
        assert out["status"] == "success"
        assert "Analysis complete" in out["result"]

    def test_returns_node_done_result(self, base_state):
        base_state["result"] = "some result"
        with patch("tools.notify.notify"):
            out = node_notify(base_state)
        assert out["status"] == "success"
        assert out["result"] == "some result"
        assert out["artifacts"] == []

    def test_notify_failure_is_graceful(self, base_state):
        """[Fix #10] A notify() failure must not prevent node_done / flip status to failed."""
        base_state["result"] = "6"
        with patch("tools.notify.notify") as mock_notify, \
             patch("core.tracer.tracer.error") as mock_error:
            mock_notify.side_effect = RuntimeError("notify-send missing")
            out = node_notify(base_state)
        assert out["status"] == "success", (
            "Notification failure must not flip a successful analysis to failed"
        )
        assert mock_error.called, "notify() failure must be logged via tracer.error"

    def test_falls_back_to_output_when_no_result(self, base_state):
        base_state["result"] = ""
        base_state["output"] = "6"
        with patch("tools.notify.notify"):
            out = node_notify(base_state)
        assert out["result"] == "6"
