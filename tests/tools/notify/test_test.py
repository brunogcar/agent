"""Tests for notify test action — verify delivery pipeline works. [NEW]

The test action sends a known test notification through the full
_send_notification chain so the LLM (or operator) can verify the delivery
pipeline is wired up correctly.

Covers:
  1. Sends a test notification (returns action_status=sent + method)
  2. Fixed title/message used (identifiable in delivery log)
  3. Delivery log entry created
  4. trace_id threading
"""
from __future__ import annotations

from tools.notify import notify
from tools.notify_ops import state


class TestTestActionSuccess:
    """test: sends test notification through delivery pipeline."""

    def test_test_sends_notification(self, mock_cfg, mock_notify_send):
        """Should send a notification and return action_status=sent."""
        result = notify(action="test")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "sent"
        assert result["data"]["action"] == "test"
        assert "method" in result["data"]
        # notify-send should have been called.
        mock_notify_send.assert_called_once()

    def test_test_uses_fixed_title_and_message(self, mock_cfg, mock_notify_send):
        """Should use fixed title='Test' message='Notification test successful'."""
        result = notify(action="test")
        assert result["data"]["title"] == "Test"
        assert result["data"]["message"] == "Notification test successful"

    def test_test_returns_method(self, mock_cfg, mock_notify_send):
        """Should return the method used (notify-send / plyer / console)."""
        result = notify(action="test")
        assert result["data"]["method"] == "notify-send"

    def test_test_on_windows_uses_plyer(self, mock_cfg, mock_plyer):
        """On Windows, should use plyer."""
        mock_cfg.is_windows = True
        result = notify(action="test")
        assert result["status"] == "success"
        assert result["data"]["method"] == "plyer"
        mock_plyer.assert_called_once()


class TestTestDeliveryLog:
    """test: delivery log entry created."""

    def test_test_appends_to_delivery_log(self, mock_cfg, mock_notify_send):
        """Should append a delivery log entry after sending the test."""
        notify(action="test")
        assert len(state._delivery_log) == 1
        entry = state._delivery_log[0]
        assert entry["title"] == "Test"
        assert entry["message"] == "Notification test successful"

    def test_test_delivery_visible_via_history(self, mock_cfg, mock_notify_send):
        """The test delivery should be visible via notify(action='history')."""
        notify(action="test")
        history_result = notify(action="history")
        assert history_result["data"]["count"] == 1
        assert history_result["data"]["notifications"][0]["title"] == "Test"


class TestTestTraceID:
    """test: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_notify_send):
        """trace_id should appear in success response."""
        result = notify(action="test", trace_id="trace-test-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-test-1"
        assert result["data"]["trace_id"] == "trace-test-1"

    def test_no_trace_id_when_not_provided(self, mock_cfg, mock_notify_send):
        """trace_id should NOT be present when not provided."""
        result = notify(action="test")
        assert result["status"] == "success"
        assert "trace_id" not in result
