"""Browser tool tests — screenshot action."""
from __future__ import annotations

from unittest.mock import AsyncMock

from tools.browser import browser


class TestScreenshot:
    """Test browser screenshot action."""

    def test_screenshot_full_page(self, mock_browser):
        result = browser(action="screenshot", trace_id="t1")
        assert result["status"] == "success"
        assert "path" in result["data"]
        mock_browser["page"].screenshot.assert_called_once()

    def test_screenshot_element(self, mock_browser):
        mock_browser["page"].query_selector = AsyncMock(return_value=mock_browser["page"])
        result = browser(action="screenshot", selector="div.chart", trace_id="t1")
        assert result["status"] == "success"
        assert "path" in result["data"]

    def test_screenshot_element_not_found(self, mock_browser):
        mock_browser["page"].query_selector = AsyncMock(return_value=None)
        result = browser(action="screenshot", selector="div.missing", trace_id="t1")
        assert result["status"] == "error"
        assert "Element not found" in result["error"]
