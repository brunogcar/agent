"""Tavily tests — error handling."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

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
        assert "api key invalid" in result["error"].lower()

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
        assert "unauthorized" in result["error"].lower() or "401" in result["error"]

    def test_httpx_http_status_error_403(self, mock_tavily_client):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_tavily_client.search.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "forbidden" in result["error"].lower() or "403" in result["error"]

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
        assert "tavily error" in result["error"].lower()

    def test_handler_returns_non_dict(self, mock_tavily_client):
        """Guard: non-dict handler return must be caught by facade."""
        with patch("tools.tavily.DISPATCH") as mock_dispatch:
            mock_dispatch.get.return_value.get.return_value = {
                "func": lambda **kw: "not a dict"
            }
            result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "returned str" in result["error"]

    def test_api_key_not_in_error_message(self, mock_tavily_client):
        """API key must never leak into error messages returned to LLM."""
        secret_key = "tvly-secret-key-abc123"
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", secret_key):
            with patch("tools.tavily_ops.errors.cfg.tavily_api_key", secret_key):
                mock_tavily_client.search.side_effect = Exception(
                    f"Auth failed for key {secret_key}"
                )
                result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert secret_key not in result["error"]
        assert "***" in result["error"]

    def test_rate_limit_backoff_retries(self, mock_tavily_client):
        """RateLimitError triggers up to 3 retry attempts with exponential backoff."""
        try:
            from tavily.errors import RateLimitError
        except ImportError:
            pytest.skip("tavily-python not installed")

        call_count = [0]
        async def _side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RateLimitError("Too many requests")
            return {"results": [{"url": "https://example.com"}], "answer": "OK"}

        mock_tavily_client.search.side_effect = _side_effect

        result = tavily(action="search", query="test")
        assert result["status"] == "success"
        assert call_count[0] == 3
