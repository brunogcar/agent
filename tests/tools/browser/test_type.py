"""Browser tool tests — type action."""
from __future__ import annotations

from tools.browser import browser


class TestType:
    """Test browser type action."""

    def test_type_success(self, mock_browser):
        result = browser(action="type", selector="input.search", value="hello", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["typed"] is True
        mock_browser["page"].type.assert_called_once_with("input.search", "hello", delay=50, timeout=30000)

    def test_type_missing_selector(self, mock_browser):
        result = browser(action="type", value="hello", trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]
