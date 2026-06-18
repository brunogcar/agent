"""Browser tool tests — fill action."""
from __future__ import annotations

from tools.browser import browser


class TestFill:
    """Test browser fill action."""

    def test_fill_success(self, mock_browser):
        result = browser(action="fill", selector="input.name", value="John", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["filled"] is True
        mock_browser["page"].fill.assert_called_once_with("input.name", "John", timeout=30000)

    def test_fill_missing_selector(self, mock_browser):
        result = browser(action="fill", value="John", trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]

    def test_fill_missing_value(self, mock_browser):
        result = browser(action="fill", selector="input.name", value=None, trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]
