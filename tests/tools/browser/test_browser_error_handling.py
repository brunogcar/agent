"""Browser tool tests — error handling."""
from __future__ import annotations

from tools.browser import browser


class TestErrorHandling:
    """Test browser error handling."""

    def test_unknown_action(self, mock_browser):
        result = browser(action="dance", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_empty_action(self, mock_browser):
        result = browser(action="", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
