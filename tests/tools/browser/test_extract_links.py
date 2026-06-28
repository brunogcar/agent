"""Browser tool tests — extract_links action."""
from __future__ import annotations

from unittest.mock import AsyncMock
from tools.browser import browser


class TestExtractLinks:
    """Test browser extract_links action."""

    def test_extract_links_default(self, mock_browser):
        mock_browser["page"].evaluate = AsyncMock(
            return_value=[
                {"href": "https://a.com", "text": "Link A", "title": ""},
                {"href": "https://b.com", "text": "Link B", "title": "B"},
            ]
        )
        result = browser(action="extract_links", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert result["data"]["links"][0]["href"] == "https://a.com"

    def test_extract_links_selector(self, mock_browser):
        mock_browser["page"].evaluate = AsyncMock(
            return_value=[{"href": "https://nav.com", "text": "Nav", "title": ""}]
        )
        result = browser(action="extract_links", selector="nav a", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 1
