"""Browser tool tests — text_content action."""
from __future__ import annotations

from tools.browser import browser


class TestTextContent:
    """Test browser text_content action."""

    def test_text_content_default(self, mock_browser):
        result = browser(action="text_content", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["text"] == "Hello World"
        assert result["data"]["selector"] == "body"

    def test_text_content_custom_selector(self, mock_browser):
        result = browser(action="text_content", selector="h1", trace_id="t1")
        assert result["status"] == "success"
        mock_browser["page"].text_content.assert_called_with("h1", timeout=30000)
