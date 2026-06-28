"""Browser tool tests — extract_tables action."""
from __future__ import annotations

from unittest.mock import AsyncMock
from tools.browser import browser


class TestExtractTables:
    """Test browser extract_tables action."""

    def test_extract_tables_default(self, mock_browser):
        mock_browser["page"].evaluate = AsyncMock(
            return_value=[
                {
                    "headers": ["Name", "Value"],
                    "rows": [["A", "1"], ["B", "2"]],
                    "row_count": 2,
                }
            ]
        )
        result = browser(action="extract_tables", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert result["data"]["tables"][0]["headers"] == ["Name", "Value"]

    def test_extract_tables_selector(self, mock_browser):
        mock_browser["page"].evaluate = AsyncMock(return_value=[])
        result = browser(
            action="extract_tables", selector=".no-tables", trace_id="t1"
        )
        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    def test_extract_tables_empty_selector_defaults_to_table(self, mock_browser):
        """When selector is empty, the handler must default to 'table', not ''."""
        mock_browser["page"].evaluate = AsyncMock(return_value=[])
        result = browser(action="extract_tables", selector="", trace_id="t1")
        assert result["status"] == "success"
        js_arg = mock_browser["page"].evaluate.call_args[0][0]
        assert 'querySelectorAll("table")' in js_arg
        assert 'querySelectorAll("")' not in js_arg

    def test_extract_tables_special_chars_in_selector(self, mock_browser):
        """Selectors with quotes must not break JS injection."""
        mock_browser["page"].evaluate = AsyncMock(return_value=[])
        result = browser(
            action="extract_tables",
            selector='table[class="data\'s"]',
            trace_id="t1",
        )
        assert result["status"] == "success"
        js_arg = mock_browser["page"].evaluate.call_args[0][0]
        assert "querySelectorAll" in js_arg

    def test_extract_tables_non_list_result(self, mock_browser):
        """If evaluate returns non-list, coerce to empty list."""
        mock_browser["page"].evaluate = AsyncMock(return_value=None)
        result = browser(action="extract_tables", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["tables"] == []
