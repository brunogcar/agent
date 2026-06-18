"""Browser tool tests — close action."""
from __future__ import annotations

from tools.browser import browser


class TestClose:
    """Test browser close action."""

    def test_close_success(self, mock_browser):
        browser(action="navigate", url="https://example.com", trace_id="t1")
        result = browser(action="close", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["closed"] is True

    def test_close_no_context(self, mock_browser):
        result = browser(action="close", trace_id="nonexistent")
        assert result["status"] == "success"  # Graceful no-op
