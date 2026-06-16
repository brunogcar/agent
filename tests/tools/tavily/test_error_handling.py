"""Tavily tool tests — error handling.

[BUGFIX-SECURITY] Fully mocked; no real Tavily API calls.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tools.tavily import tavily, _get_client, _handle_tavily_error


# ── Shared fixtures (each file is self-contained) ───────────────────────────

@pytest.fixture(autouse=True)
def reset_tavily_state():
    """Reset Tavily client singleton before each test."""
    from tools import tavily as tavily_mod
    tavily_mod._tavily_client = None
    tavily_mod._tavily_client_key = None
    tavily_mod._keyless_warned = False
    yield
    tavily_mod._tavily_client = None
    tavily_mod._tavily_client_key = None
    tavily_mod._keyless_warned = False


@pytest.fixture(autouse=True)
def mock_cfg_for_tavily():
    """Mock cfg to prevent AsyncMock leakage and provide Tavily defaults."""
    with patch("tools.tavily.cfg") as mock_cfg:
        mock_cfg.tavily_api_key = "tvly-test-key-123"
        mock_cfg.tavily_timeout = 60
        # Prevent CLI/other cross-test bleed
        mock_cfg.cli_max_command_chars = 4096
        mock_cfg.cli_max_arguments = 50
        yield mock_cfg


@pytest.fixture
def mock_tavily_client():
    """Return a mock AsyncTavilyClient with awaitable async methods."""
    client = MagicMock()
    client.search = AsyncMock(return_value={
        "results": [
            {"url": "https://example.com", "title": "Example", "content": "Hello"}
        ],
        "answer": "Test answer",
    })
    client.extract = AsyncMock(return_value={
        "results": [{"url": "https://example.com", "raw_content": "Extracted text"}]
    })
    client.crawl = AsyncMock(return_value={
        "results": [{"url": "https://example.com/page1", "title": "Page 1"}]
    })
    client.map = AsyncMock(return_value={
        "results": [{"url": "https://example.com/sitemap", "title": "Sitemap"}]
    })
    with patch("tools.tavily._get_client", return_value=client):
        yield client


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
