"""Browser tool tests — navigate action."""
from __future__ import annotations

from unittest.mock import patch, AsyncMock
from tools.browser import browser


class TestNavigate:
    """Test browser navigate action."""

    def test_navigate_success(self, mock_browser):
        result = browser(
            action="navigate", url="https://example.com", trace_id="t1"
        )
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        assert result["data"]["title"] == "Example Page"
        mock_browser["page"].goto.assert_called_once_with(
            "https://example.com", wait_until="domcontentloaded", timeout=30000
        )

    def test_navigate_missing_url(self, mock_browser):
        result = browser(action="navigate", trace_id="t1")
        assert result["status"] == "error"
        assert "url is required" in result["error"]

    def test_navigate_ssrf_blocked(self, mock_browser):
        with patch(
            "tools.browser_core.actions.navigate.is_safe_network_address",
            return_value=False,
        ):
            result = browser(
                action="navigate", url="http://127.0.0.1/admin", trace_id="t1"
            )
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_invalid_scheme_file(self, mock_browser):
        """file:// scheme must be blocked before any network call."""
        result = browser(
            action="navigate", url="file:///etc/passwd", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "Invalid URL scheme" in result["error"]
        mock_browser["page"].goto.assert_not_called()

    def test_navigate_invalid_scheme_javascript(self, mock_browser):
        """javascript: scheme must be blocked."""
        result = browser(
            action="navigate", url="javascript:alert(1)", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "Invalid URL scheme" in result["error"]
        mock_browser["page"].goto.assert_not_called()

    def test_navigate_timeout(self, mock_browser):
        mock_browser["page"].goto.side_effect = Exception("Timeout")
        result = browser(
            action="navigate", url="https://example.com", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "Navigation failed" in result["error"]

    def test_navigate_retry_succeeds_on_second_attempt(self, mock_browser):
        """Retry: first attempt fails, second succeeds. Verify via goto call count."""
        mock_browser["page"].goto.side_effect = [
            Exception("Network timeout"),  # first attempt fails
            None,  # second attempt succeeds
        ]
        result = browser(
            action="navigate",
            url="https://example.com",
            retries=1,
            trace_id="t1",
        )
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        assert mock_browser["page"].goto.call_count == 2

    def test_navigate_retry_exhausts(self, mock_browser):
        """All retries exhausted — returns the last error with attempt count."""
        mock_browser["page"].goto.side_effect = Exception("Persistent failure")
        result = browser(
            action="navigate",
            url="https://example.com",
            retries=2,
            trace_id="t1",
        )
        assert result["status"] == "error"
        assert "after 3 attempt(s)" in result["error"]
        assert "Persistent failure" in result["error"]
        # 2 retries = 3 total attempts (initial + 2 retries)
        assert mock_browser["page"].goto.call_count == 3

    def test_navigate_retry_zero_no_retry(self, mock_browser):
        """retries=0 means no retry — single attempt only."""
        mock_browser["page"].goto.side_effect = Exception("fail")
        result = browser(
            action="navigate",
            url="https://example.com",
            retries=0,
            trace_id="t1",
        )
        assert result["status"] == "error"
        assert mock_browser["page"].goto.call_count == 1
