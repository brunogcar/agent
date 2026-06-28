"""Browser tool tests — close action."""
from __future__ import annotations

from tools.browser import browser


class TestClose:
    """Test browser close action."""

    def test_close_with_trace_id(self, mock_browser):
        """Close with trace_id should succeed (best-effort cleanup)."""
        result = browser(action="close", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["closed"] is True

    def test_close_without_trace_id(self, mock_browser):
        """close() without trace_id must return an error, not silently succeed."""
        result = browser(action="close")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]

    def test_close_unknown_trace_id(self, mock_browser):
        """Closing a non-existent trace should succeed (nothing to close)."""
        result = browser(action="close", trace_id="unknown_trace")
        assert result["status"] == "success"
        assert result["data"]["closed"] is True
