"""Browser tool tests — get_url action."""
from __future__ import annotations

from tools.browser import browser


class TestGetUrl:
    """Test browser get_url action."""

    def test_get_url_success(self, mock_browser):
        result = browser(action="get_url", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"

    def test_get_url_after_navigate(self, mock_browser):
        browser(action="navigate", url="https://example.com", trace_id="t1")
        result = browser(action="get_url", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
