"""Browser tool tests — extract_html action."""
from __future__ import annotations

from tools.browser import browser


class TestExtractHtml:
    """Test browser extract_html action."""

    def test_extract_html_full_page(self, mock_browser):
        result = browser(action="extract_html", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["html"] == "<html></html>"
        assert result["data"]["selector"] == "body"
        mock_browser["page"].content.assert_called_once()

    def test_extract_html_element(self, mock_browser):
        result = browser(action="extract_html", selector="table.data", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["html"] == "<div>html</div>"
        mock_browser["page"].inner_html.assert_called_once_with("table.data", timeout=30000)
