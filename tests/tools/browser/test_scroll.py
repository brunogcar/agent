"""tests/tools/browser/test_scroll.py

Phase 3: scroll action â€" scroll page or element.
"""
import pytest
from unittest.mock import AsyncMock

from tools.browser import browser


class TestScroll:
    """Test browser scroll action."""

    def test_scroll_bottom_success(self, mock_browser):
        result = browser(action="scroll", direction="bottom", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["scrolled"] is True
        assert result["data"]["direction"] == "bottom"
        mock_browser["page"].evaluate.assert_called_once_with("window.scrollTo(0, document.body.scrollHeight)")

    def test_scroll_top_success(self, mock_browser):
        result = browser(action="scroll", direction="top", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["direction"] == "top"
        mock_browser["page"].evaluate.assert_called_once_with("window.scrollTo(0, 0)")

    def test_scroll_element_success(self, mock_browser):
        mock_element = AsyncMock()
        mock_element.scroll_into_view_if_needed = AsyncMock(return_value=None)
        mock_browser["page"].query_selector = AsyncMock(return_value=mock_element)
        result = browser(action="scroll", selector="#target", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["selector"] == "#target"
        mock_browser["page"].query_selector.assert_called_once_with("#target")
        mock_element.scroll_into_view_if_needed.assert_called_once()

    def test_scroll_element_not_found(self, mock_browser):
        mock_browser["page"].query_selector = AsyncMock(return_value=None)
        result = browser(action="scroll", selector="#missing", trace_id="t1")
        assert result["status"] == "error"
        assert "Element not found" in result["error"]

    def test_scroll_down_with_amount(self, mock_browser):
        result = browser(action="scroll", direction="down", amount=500, trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["amount"] == 500
        mock_browser["page"].evaluate.assert_called_once_with("window.scrollBy(0, 500)")
