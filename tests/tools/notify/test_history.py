"""Tests for notify history action — recently sent notifications log. [NEW]

Covers:
  1. Returns the log (with at least one entry after a send)
  2. Empty log when nothing sent yet
  3. trace_id threading
  4. Log is bounded (max 50 entries) — last-20 slice returned
"""
from __future__ import annotations

from tools.notify import notify
from tools.notify_ops import state


class TestHistorySuccess:
    """history: returns recently sent notifications."""

    def test_history_returns_log_after_send(self, mock_cfg, mock_notify_send):
        """Should return the delivery log entry created by a prior send."""
        notify(action="send", title="T1", message="M1")
        result = notify(action="history")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "ok"
        assert result["data"]["action"] == "history"
        assert result["data"]["count"] == 1
        assert result["data"]["total_logged"] == 1
        notif = result["data"]["notifications"][0]
        assert notif["title"] == "T1"
        assert notif["message"] == "M1"
        assert notif["method"] == "notify-send"
        assert "timestamp" in notif

    def test_history_returns_multiple_entries(self, mock_cfg, mock_notify_send):
        """Multiple sends should produce multiple log entries."""
        notify(action="send", message="first")
        notify(action="send", message="second")
        notify(action="send", message="third")
        result = notify(action="history")
        assert result["data"]["count"] == 3
        messages = [n["message"] for n in result["data"]["notifications"]]
        assert messages == ["first", "second", "third"]


class TestHistoryEmpty:
    """history: empty log when nothing sent."""

    def test_history_empty_log(self, mock_cfg, mock_notify_send):
        """Should return empty list when no notifications sent yet."""
        result = notify(action="history")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["total_logged"] == 0
        assert result["data"]["notifications"] == []


class TestHistoryBounded:
    """history: log bounded to 50 entries, response returns last 20."""

    def test_history_log_capped_at_50(self, mock_cfg, mock_notify_send):
        """Delivery log should be capped at 50 entries (older entries dropped)."""
        # Send 60 notifications — log should only keep the last 50.
        for i in range(60):
            notify(action="send", message=f"msg-{i}")

        result = notify(action="history")
        # total_logged should be capped at 50.
        assert result["data"]["total_logged"] == 50
        # Response should return at most 20.
        assert result["data"]["count"] == 20
        # The oldest 10 messages (msg-0 through msg-9) should be dropped.
        messages = [n["message"] for n in result["data"]["notifications"]]
        assert "msg-0" not in messages
        assert "msg-9" not in messages
        # The most recent 20 should be present (msg-40 through msg-59).
        assert "msg-40" in messages
        assert "msg-59" in messages
        # And in order.
        assert messages[0] == "msg-40"
        assert messages[-1] == "msg-59"


class TestHistoryTraceID:
    """history: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_notify_send):
        """trace_id should appear in success response."""
        notify(action="send", message="hi")
        result = notify(action="history", trace_id="trace-hist-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-hist-1"
        assert result["data"]["trace_id"] == "trace-hist-1"
