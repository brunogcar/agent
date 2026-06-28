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
        result = browser(
            action="extract_links", selector="nav a", trace_id="t1"
        )
        assert result["status"] == "success"
        assert result["data"]["count"] == 1

    def test_extract_links_empty_selector_defaults_to_a(self, mock_browser):
        """When selector is empty, the handler must default to 'a', not ''."""
        mock_browser["page"].evaluate = AsyncMock(return_value=[])
        result = browser(action="extract_links", selector="", trace_id="t1")
        assert result["status"] == "success"
        # Verify the JS was called with "a" not ""
        js_arg = mock_browser["page"].evaluate.call_args[0][0]
        assert 'querySelectorAll("a")' in js_arg
        assert 'querySelectorAll("")' not in js_arg

    def test_extract_links_special_chars_in_selector(self, mock_browser):
        """Selectors with quotes and backslashes must not break JS injection."""
        mock_browser["page"].evaluate = AsyncMock(return_value=[])
        result = browser(
            action="extract_links",
            selector='a[data-value="it\'s"]',
            trace_id="t1",
        )
        assert result["status"] == "success"
        # Verify the JS contains a properly escaped string
        js_arg = mock_browser["page"].evaluate.call_args[0][0]
        assert "querySelectorAll" in js_arg

    def test_extract_links_non_list_result(self, mock_browser):
        """If evaluate returns non-list, coerce to empty list."""
        mock_browser["page"].evaluate = AsyncMock(return_value=None)
        result = browser(action="extract_links", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["links"] == []
