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
        result = browser(action="extract_tables", selector=".no-tables", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
