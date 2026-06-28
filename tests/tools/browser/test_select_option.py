"""Browser tool tests — select_option action."""
from __future__ import annotations

from tools.browser import browser


class TestSelectOption:
    """Test browser select_option action."""

    def test_select_option_success(self, mock_browser):
        result = browser(
            action="select_option",
            selector="select.country",
            value="US",
            trace_id="t1",
        )
        assert result["status"] == "success"
        assert result["data"]["selected"] == "US"
        assert result["data"]["selector"] == "select.country"
        mock_browser["page"].select_option.assert_called_once_with(
            "select.country", "US", timeout=30000
        )

    def test_select_option_missing_selector(self, mock_browser):
        result = browser(action="select_option", value="US", trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]

    def test_select_option_empty_value_allowed(self, mock_browser):
        """Empty string is a valid select_option value (may select empty option)."""
        result = browser(
            action="select_option",
            selector="select.country",
            value="",
            trace_id="t1",
        )
        assert result["status"] == "success"
        assert result["data"]["selected"] == ""
