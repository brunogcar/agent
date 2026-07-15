"""Tests for notify send action — immediate desktop notification.

Covers:
  1. Success path on Linux (notify-send)
  2. Success path on Windows (plyer)
  3. Missing message → error
  4. Console fallback when plyer raises
  5. Console fallback when notify-send not installed (FileNotFoundError)
  6. trace_id in response (success + error)
  7. Delivery log entry created (verifiable via history action)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.notify import notify
from tools.notify_ops import state


class TestSendSuccess:
    """send: immediate notification success paths."""

    def test_send_success_on_linux(self, mock_cfg, mock_notify_send):
        """Should deliver via notify-send on Linux and return action_status=sent."""
        result = notify(action="send", message="Build finished")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "sent"
        assert result["data"]["action"] == "send"
        assert result["data"]["title"] == "Agent"  # default
        assert result["data"]["message"] == "Build finished"
        assert result["data"]["method"] == "notify-send"
        mock_notify_send.assert_called_once()

    def test_send_success_on_windows(self, mock_cfg, mock_plyer):
        """Should deliver via plyer on Windows and return action_status=sent."""
        mock_cfg.is_windows = True
        result = notify(action="send", title="Hi", message="Build finished")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "sent"
        assert result["data"]["method"] == "plyer"
        assert result["data"]["title"] == "Hi"
        mock_plyer.assert_called_once()

    def test_send_default_title_is_agent(self, mock_cfg, mock_notify_send):
        """When title is empty, default 'Agent' should be used."""
        result = notify(action="send", message="hi")
        assert result["data"]["title"] == "Agent"


class TestSendValidation:
    """send: parameter validation."""

    def test_send_missing_message(self, mock_cfg, mock_notify_send):
        """Should return error when message is empty."""
        result = notify(action="send", message="")
        assert result["status"] == "error"
        assert result["data"] is None
        assert "message is required" in result["error"]
        assert result.get("error_code") == "MISSING_PARAM"
        # notify-send should NOT have been called
        mock_notify_send.assert_not_called()


class TestSendFallback:
    """send: graceful fallback to console when primary backend fails."""

    def test_send_console_fallback_when_plyer_raises(self, mock_cfg, mock_plyer):
        """If plyer raises, should fall back to console and still return success."""
        mock_cfg.is_windows = True
        mock_plyer.side_effect = Exception("Plyer crashed")
        result = notify(action="send", message="test fallback")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "sent"
        assert result["data"]["method"] == "console"

    def test_send_console_fallback_when_notify_send_missing(self, mock_cfg, mock_notify_send):
        """If notify-send binary is missing (FileNotFoundError), fall back to console."""
        mock_notify_send.side_effect = FileNotFoundError("notify-send not installed")
        result = notify(action="send", message="test fallback")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "sent"
        assert result["data"]["method"] == "console"

    def test_send_console_fallback_when_notify_send_returns_nonzero(self, mock_cfg, mock_notify_send):
        """If notify-send exits nonzero, fall back to console."""
        fail_result = MagicMock()
        fail_result.returncode = 1
        mock_notify_send.return_value = fail_result
        result = notify(action="send", message="test fallback")
        assert result["status"] == "success"
        assert result["data"]["method"] == "console"


class TestSendTraceID:
    """send: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_notify_send):
        """trace_id should appear in success response."""
        result = notify(action="send", message="hi", trace_id="trace-send-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-send-1"
        assert result["data"]["trace_id"] == "trace-send-1"  # also in data via ok()

    def test_trace_id_in_error_response(self, mock_cfg, mock_notify_send):
        """trace_id should appear in error response."""
        result = notify(action="send", message="", trace_id="trace-send-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-send-2"

    def test_no_trace_id_when_not_provided(self, mock_cfg, mock_notify_send):
        """trace_id should NOT be present when not provided."""
        result = notify(action="send", message="hi")
        assert result["status"] == "success"
        # trace_id only added to response when explicitly provided
        assert "trace_id" not in result


class TestSendDeliveryLog:
    """send: delivery log entry created by _send_notification."""

    def test_send_appends_to_delivery_log(self, mock_cfg, mock_notify_send):
        """send should append a record to state._delivery_log."""
        notify(action="send", title="TestTitle", message="TestMessage")
        assert len(state._delivery_log) == 1
        entry = state._delivery_log[0]
        assert entry["title"] == "TestTitle"
        assert entry["message"] == "TestMessage"
        assert entry["method"] == "notify-send"
        assert "timestamp" in entry

    def test_send_delivery_visible_via_history_action(self, mock_cfg, mock_notify_send):
        """The delivery log entry should be visible via notify(action='history')."""
        notify(action="send", message="hello from send test")
        history_result = notify(action="history")
        assert history_result["status"] == "success"
        assert history_result["data"]["count"] == 1
        assert history_result["data"]["notifications"][0]["message"] == "hello from send test"
