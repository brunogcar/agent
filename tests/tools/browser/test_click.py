"""Browser tool tests — click action."""
from __future__ import annotations

from tools.browser import browser


class TestClick:
    """Test browser click action."""

    def test_click_success(self, mock_browser):
        result = browser(action="click", selector="button.submit", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["clicked"] is True
        mock_browser["page"].click.assert_called_once_with("button.submit", timeout=30000)

    def test_click_missing_selector(self, mock_browser):
        result = browser(action="click", trace_id="t1")
        assert result["status"] == "error"
        assert "selector is required" in result["error"]
