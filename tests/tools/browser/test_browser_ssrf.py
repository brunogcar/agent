"""Browser tool tests — SSRF protection."""
from __future__ import annotations

from unittest.mock import patch
from tools.browser import browser


class TestSSRF:
    """Test browser SSRF blocking."""

    def test_navigate_private_ip(self, mock_browser):
        with patch("tools.browser_core.actions.navigate.is_safe_network_address", return_value=False):
            result = browser(action="navigate", url="http://192.168.1.1", trace_id="t1")
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_localhost(self, mock_browser):
        with patch("tools.browser_core.actions.navigate.is_safe_network_address", return_value=False):
            result = browser(action="navigate", url="http://localhost:8080", trace_id="t1")
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_public_allowed(self, mock_browser):
        result = browser(action="navigate", url="https://github.com", trace_id="t1")
        assert result["status"] == "success"
