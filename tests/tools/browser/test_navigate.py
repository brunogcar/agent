"""Browser tool tests — navigate action."""
from __future__ import annotations

from tools.browser import browser


class TestNavigate:
    """Test browser navigate action."""

    def test_navigate_success(self, mock_browser):
        result = browser(action="navigate", url="https://example.com", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        assert result["data"]["title"] == "Example Page"
        mock_browser["page"].goto.assert_called_once()

    def test_navigate_missing_url(self, mock_browser):
        result = browser(action="navigate", trace_id="t1")
        assert result["status"] == "error"
        assert "url is required" in result["error"]

    def test_navigate_ssrf_blocked(self, mock_browser):
        from unittest.mock import patch
        with patch("tools.browser_core.actions.is_safe_network_address", return_value=False):
            result = browser(action="navigate", url="http://127.0.0.1/admin", trace_id="t1")
        assert result["status"] == "error"
        assert "SSRF blocked" in result["error"]

    def test_navigate_timeout(self, mock_browser):
        mock_browser["page"].goto.side_effect = Exception("Timeout")
        result = browser(action="navigate", url="https://example.com", trace_id="t1", timeout=1)
        assert result["status"] == "error"
        assert "Navigation failed" in result["error"]
