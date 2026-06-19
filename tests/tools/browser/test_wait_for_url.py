"""tests/tools/browser/test_wait_for_url.py

Phase 3: wait_for_url action â€" waits for current URL to match a pattern.
"""
import pytest
from unittest.mock import AsyncMock

from tools.browser import browser


class TestWaitForUrl:
    """Test browser wait_for_url action."""

    def test_wait_for_url_success(self, mock_browser):
        mock_browser["page"].wait_for_url = AsyncMock(return_value=None)
        result = browser(action="wait_for_url", url="**/dashboard", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["waited"] is True
        assert result["data"]["url"] == "https://example.com"
        mock_browser["page"].wait_for_url.assert_called_once_with("**/dashboard", timeout=30000)

    def test_wait_for_url_missing_url(self, mock_browser):
        result = browser(action="wait_for_url", trace_id="t1")
        assert result["status"] == "error"
        assert "url is required" in result["error"]

    def test_wait_for_url_timeout(self, mock_browser):
        mock_browser["page"].wait_for_url = AsyncMock(side_effect=Exception("Timeout"))
        result = browser(action="wait_for_url", url="https://never-arrives.com", timeout=1, trace_id="t1")
        assert result["status"] == "error"
        assert "wait_for_url failed" in result["error"]
