"""Browser tool tests — SSRF blocking."""
from __future__ import annotations

from unittest.mock import patch
from tools.browser import browser


class TestSSRF:
    """Test browser SSRF blocking."""

    def test_navigate_private_ip(self, mock_browser):
        with patch(
            "tools.browser_core.actions.navigate.is_safe_network_address",
            return_value=False,
        ):
            result = browser(
                action="navigate", url="http://192.168.1.1", trace_id="t1"
            )
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_localhost(self, mock_browser):
        with patch(
            "tools.browser_core.actions.navigate.is_safe_network_address",
            return_value=False,
        ):
            result = browser(
                action="navigate", url="http://localhost:8080", trace_id="t1"
            )
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_public_allowed(self, mock_browser):
        result = browser(
            action="navigate", url="https://github.com", trace_id="t1"
        )
        assert result["status"] == "success"

    def test_navigate_file_scheme_blocked(self, mock_browser):
        """file:// URLs must be rejected before any network call."""
        result = browser(
            action="navigate", url="file:///etc/passwd", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "Invalid URL scheme" in result["error"]
        mock_browser["page"].goto.assert_not_called()

    def test_navigate_javascript_scheme_blocked(self, mock_browser):
        """javascript: URLs must be rejected."""
        result = browser(
            action="navigate", url="javascript:alert(1)", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "Invalid URL scheme" in result["error"]
        mock_browser["page"].goto.assert_not_called()

    def test_navigate_data_scheme_blocked(self, mock_browser):
        """data: URLs must be rejected."""
        result = browser(
            action="navigate",
            url="data:text/html,<script>alert(1)</script>",
            trace_id="t1",
        )
        assert result["status"] == "error"
        assert "Invalid URL scheme" in result["error"]
        mock_browser["page"].goto.assert_not_called()
