"""Browser tool tests — cookies action."""
from __future__ import annotations

from unittest.mock import AsyncMock
from tools.browser import browser


class TestCookies:
    """Test browser cookies action."""

    def test_cookies_get(self, mock_browser):
        mock_browser["context"].cookies = AsyncMock(return_value=[{"name": "session", "value": "abc"}])
        result = browser(action="cookies", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        mock_browser["context"].cookies.assert_called_once()

    def test_cookies_set(self, mock_browser):
        mock_browser["context"].add_cookies = AsyncMock(return_value=None)
        result = browser(action="cookies", action_detail="set", cookies_json='[{"name":"x","value":"y","url":"https://example.com"}]', trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["cookies_set"] == 1
        mock_browser["context"].add_cookies.assert_called_once()

    def test_cookies_clear(self, mock_browser):
        mock_browser["context"].clear_cookies = AsyncMock(return_value=None)
        result = browser(action="cookies", action_detail="clear", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["cookies_cleared"] is True
        mock_browser["context"].clear_cookies.assert_called_once()

    def test_cookies_unknown_action(self, mock_browser):
        result = browser(action="cookies", action_detail="delete_all", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown cookies action_detail" in result["error"]
