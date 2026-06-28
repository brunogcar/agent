"""Browser tool tests — hover action."""
from __future__ import annotations

from tools.browser import browser


class TestHover:
    """Test browser hover action."""

    def test_hover_success(self, mock_browser):
        result = browser(action="hover", selector=".menu-item", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["hovered"] is True
        assert result["data"]["selector"] == ".menu-item"
        mock_browser["page"].hover.assert_called_once_with(".menu-item", timeout=30000)

    def test_hover_missing_selector(self, mock_browser):
        result = browser(action="hover", trace_id="t1")
        assert result["status"] == "error"
        assert "selector is required" in result["error"]
