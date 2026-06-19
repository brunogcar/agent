"""tests/tools/browser/test_wait_for_selector.py

Phase 3: wait_for_selector action â€" waits for an element to appear in the DOM.
"""
import pytest

from tools.browser import browser


class TestWaitForSelector:
    """Test browser wait_for_selector action."""

    def test_wait_for_selector_success(self, mock_browser):
        result = browser(action="wait_for_selector", selector="div.content", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["waited"] is True
        assert result["data"]["selector"] == "div.content"
        mock_browser["page"].wait_for_selector.assert_called_once_with("div.content", timeout=30000)

    def test_wait_for_selector_missing_selector(self, mock_browser):
        result = browser(action="wait_for_selector", trace_id="t1")
        assert result["status"] == "error"
        assert "selector is required" in result["error"]

    def test_wait_for_selector_timeout(self, mock_browser):
        mock_browser["page"].wait_for_selector.side_effect = Exception("Timeout")
        result = browser(action="wait_for_selector", selector="div.never-appears", timeout=1, trace_id="t1")
        assert result["status"] == "error"
        assert "wait_for_selector failed" in result["error"]
