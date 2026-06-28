"""Browser tool tests — cookies action."""
from __future__ import annotations

from unittest.mock import AsyncMock
from tools.browser import browser


class TestCookies:
    """Test browser cookies action."""

    def test_cookies_get(self, mock_browser):
        mock_browser["context"].cookies = AsyncMock(
            return_value=[{"name": "session", "value": "abc"}]
        )
        result = browser(action="cookies", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        mock_browser["context"].cookies.assert_called_once_with()

    def test_cookies_get_with_url_filter(self, mock_browser):
        """URL filter passes urls=[...] to context.cookies()."""
        mock_browser["context"].cookies = AsyncMock(return_value=[])
        result = browser(
            action="cookies",
            action_detail="get",
            url="https://example.com",
            trace_id="t1",
        )
        assert result["status"] == "success"
        mock_browser["context"].cookies.assert_called_once_with(
            urls=["https://example.com"]
        )

    def test_cookies_set(self, mock_browser):
        mock_browser["context"].add_cookies = AsyncMock(return_value=None)
        result = browser(
            action="cookies",
            action_detail="set",
            cookies_json='[{"name":"x","value":"y","url":"https://example.com"}]',
            trace_id="t1",
        )
        assert result["status"] == "success"
        assert result["data"]["cookies_set"] == 1
        mock_browser["context"].add_cookies.assert_called_once()

    def test_cookies_set_invalid_json(self, mock_browser):
        """Malformed JSON must return a specific error, not a generic crash."""
        result = browser(
            action="cookies",
            action_detail="set",
            cookies_json="not json",
            trace_id="t1",
        )
        assert result["status"] == "error"
        assert "Invalid cookies JSON" in result["error"]

    def test_cookies_set_not_a_list(self, mock_browser):
        """Non-array JSON must be rejected."""
        result = browser(
            action="cookies",
            action_detail="set",
            cookies_json='{"name":"x","value":"y"}',
            trace_id="t1",
        )
        assert result["status"] == "error"
        assert "JSON array" in result["error"]

    def test_cookies_set_missing_name_value(self, mock_browser):
        """Cookie missing required name/value fields must be rejected."""
        result = browser(
            action="cookies",
            action_detail="set",
            cookies_json='[{"value":"y","url":"https://example.com"}]',
            trace_id="t1",
        )
        assert result["status"] == "error"
        assert "missing required" in result["error"]

    def test_cookies_set_missing_url_and_domain(self, mock_browser):
        """Cookie needs either url or domain+path."""
        result = browser(
            action="cookies",
            action_detail="set",
            cookies_json='[{"name":"x","value":"y"}]',
            trace_id="t1",
        )
        assert result["status"] == "error"
        assert "needs 'url' or 'domain'+'path'" in result["error"]

    def test_cookies_set_empty_json(self, mock_browser):
        """Empty cookies_json with set action must return an error."""
        result = browser(
            action="cookies", action_detail="set", cookies_json="", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "cookies_json is required" in result["error"]

    def test_cookies_clear(self, mock_browser):
        mock_browser["context"].clear_cookies = AsyncMock(return_value=None)
        result = browser(action="cookies", action_detail="clear", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["cookies_cleared"] is True
        mock_browser["context"].clear_cookies.assert_called_once()

    def test_cookies_unknown_action(self, mock_browser):
        result = browser(
            action="cookies", action_detail="delete_all", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "Unknown cookies action_detail" in result["error"]
