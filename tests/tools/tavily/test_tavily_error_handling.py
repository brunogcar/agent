"""Tavily tests — error handling."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tools.tavily import tavily
from tools.tavily_ops.errors import _handle_tavily_error


class TestErrorHandling:
    """Test tavily error handling paths."""

    def test_tavily_keyless_limit_error(self, mock_tavily_client):
        try:
            from tavily.errors import TavilyKeylessLimitError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = TavilyKeylessLimitError("Rate limit reached")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "keyless rate limit reached" in result["error"].lower()

    def test_tavily_invalid_key_error(self, mock_tavily_client):
        try:
            from tavily.errors import InvalidAPIKeyError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = InvalidAPIKeyError("Invalid key")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "API key invalid" in result["error"]

    def test_usage_limit_exceeded_error(self, mock_tavily_client):
        try:
            from tavily.errors import UsageLimitExceededError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = UsageLimitExceededError("Monthly quota exceeded")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "quota exhausted" in result["error"].lower()

    def test_tavily_api_error_429(self, mock_tavily_client):
        try:
            from tavily.errors import TavilyAPIError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = TavilyAPIError("Rate limited", status_code=429)
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "429" in result["error"] or "rate limit" in result["error"].lower()

    def test_httpx_timeout(self, mock_tavily_client):
        import httpx
        mock_tavily_client.search.side_effect = httpx.TimeoutException("Request timed out")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "timed out" in result["error"].lower()

    def test_httpx_connect_error(self, mock_tavily_client):
        import httpx
        mock_tavily_client.search.side_effect = httpx.ConnectError("Connection refused")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "connect" in result["error"].lower()

    def test_httpx_http_status_error_401(self, mock_tavily_client):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_tavily_client.search.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "authentication" in result["error"].lower()

    def test_httpx_http_status_error_403(self, mock_tavily_client):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_tavily_client.search.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "authentication" in result["error"].lower() or "403" in result["error"]

    def test_httpx_http_status_error_429(self, mock_tavily_client):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_tavily_client.search.side_effect = httpx.HTTPStatusError(
            "Rate Limited", request=MagicMock(), response=mock_response
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "429" in result["error"] or "rate limit" in result["error"].lower()

    def test_unknown_tavily_error(self, mock_tavily_client):
        mock_tavily_client.search.side_effect = Exception("Something weird")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "Tavily error" in result["error"]

    def test_handler_returns_non_dict(self, mock_tavily_client):
        """Guard: non-dict handler return must be caught."""
        mock_tavily_client.search.return_value = "not a dict"
        result = tavily(action="search", query="test")
        # The mock returns a string, which the action handler wraps in ok()
        # but if a handler ever returned a non-dict directly, the facade catches it
        assert result["status"] == "error"
