"""Browser tool tests — extract_html action."""
from __future__ import annotations

from tools.browser import browser


class TestExtractHtml:
    """Test browser extract_html action."""

    def test_extract_html_full_page(self, mock_browser):
        result = browser(action="extract_html", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["html"] == ""
        # Full page HTML should be labeled "full_page", not "body"
        assert result["data"]["selector"] == "full_page"
        mock_browser["page"].content.assert_called_once()

    def test_extract_html_element(self, mock_browser):
        result = browser(
            action="extract_html", selector="table.data", trace_id="t1"
        )
        assert result["status"] == "success"
        assert result["data"]["html"] == "<div>html</div>"
        assert result["data"]["selector"] == "table.data"
        mock_browser["page"].inner_html.assert_called_once_with(
            "table.data", timeout=30000
        )

    def test_extract_html_element_not_found(self, mock_browser):
        """inner_html on missing selector should propagate as error."""
        mock_browser["page"].inner_html.side_effect = Exception(
            "Element not found"
        )
        result = browser(
            action="extract_html", selector="div.missing", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "extract_html failed" in result["error"]
