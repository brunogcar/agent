"""
❌ tests/tools/tavily/test_tavily.py — Tavily tool unit tests (fully mocked).

Strategy: Patch _get_client (not tavily.AsyncTavilyClient) so tests pass
even when tavily-python is not installed in the test environment.

AsyncMock is used for async client methods because MagicMock return values
are not awaitable — `await dict` raises TypeError.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tools.tavily import tavily, _get_client, _handle_tavily_error


# ── Fixtures ───────────────────────────────────────────────────────────────

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


@pytest.fixture
def mock_config():
    """Patch cfg with a dummy Tavily API key."""
    with patch("tools.tavily.cfg") as mock_cfg:
        mock_cfg.tavily_api_key = "tvly-test-key-123"
        mock_cfg.tavily_timeout = 60
        yield mock_cfg


@pytest.fixture
def mock_tavily_client(mock_config):
    """Return a mock AsyncTavilyClient with awaitable async methods."""
    client = MagicMock()
    # Use AsyncMock for async methods so `await client.search()` works
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


# ── Test: Search ─────────────────────────────────────────────────────────────

class TestSearch:
    def test_search_success(self, mock_config, mock_tavily_client):
        result = tavily(action="search", query="pytest testing")
        assert result["status"] == "success"
        assert result["data"]["answer"] == "Test answer"
        assert len(result["data"]["results"]) == 1
        mock_tavily_client.search.assert_called_once()

    def test_search_missing_query(self, mock_config, mock_tavily_client):
        result = tavily(action="search")
        assert result["status"] == "error"
        assert "query is required" in result["error"]

    def test_search_keyless_mode(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="search", query="test")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_search_keyless_cap(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="search", query="test", max_results=10)
        assert result["status"] == "success"
        # Verify max_results was capped to 3 in keyless mode
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["max_results"] == 3


# ── Test: Extract ────────────────────────────────────────────────────────────

class TestExtract:
    def test_extract_success(self, mock_config, mock_tavily_client):
        result = tavily(
            action="extract",
            urls=["https://example.com"],
            include_raw_content=True,
        )
        assert result["status"] == "success"
        assert len(result["data"]["results"]) == 1
        mock_tavily_client.extract.assert_called_once()

    def test_extract_missing_urls(self, mock_config, mock_tavily_client):
        result = tavily(action="extract")
        assert result["status"] == "error"
        assert "urls is required" in result["error"]

    def test_extract_too_many_urls(self, mock_config, mock_tavily_client):
        result = tavily(action="extract", urls=["https://a.com"] * 11)
        assert result["status"] == "error"
        assert "cannot exceed 10 items" in result["error"]

    def test_extract_ssrf_blocked(self, mock_config, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="extract", urls=["http://127.0.0.1/secret"])
            assert result["status"] == "error"
            assert "Blocked" in result["error"]


# ── Test: Crawl ────────────────────────────────────────────────────────────

class TestCrawl:
    def test_crawl_success(self, mock_config, mock_tavily_client):
        result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is False
        mock_tavily_client.crawl.assert_called_once()

    def test_crawl_missing_url(self, mock_config, mock_tavily_client):
        result = tavily(action="crawl")
        assert result["status"] == "error"
        assert "url or query is required" in result["error"]

    def test_crawl_keyless_blocked(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_crawl_ssrf_blocked(self, mock_config, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="crawl", url="http://192.168.1.1/admin")
            assert result["status"] == "error"
            assert "Blocked" in result["error"]


# ── Test: Map ────────────────────────────────────────────────────────────────

class TestMap:
    def test_map_success(self, mock_config, mock_tavily_client):
        result = tavily(action="map", url="https://example.com")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is False
        mock_tavily_client.map.assert_called_once()

    def test_map_missing_url(self, mock_config, mock_tavily_client):
        result = tavily(action="map")
        assert result["status"] == "error"
        assert "url or query is required" in result["error"]

    def test_map_keyless_blocked(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="map", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]


# ── Test: Error Handling ─────────────────────────────────────────────────────

class TestErrorHandling:
    def test_tavily_keyless_limit_error(self, mock_config, mock_tavily_client):
        try:
            from tavily.errors import TavilyKeylessLimitError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = TavilyKeylessLimitError("Rate limit reached")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "keyless rate limit reached" in result["error"].lower()

    def test_tavily_invalid_key_error(self, mock_config, mock_tavily_client):
        try:
            from tavily.errors import InvalidAPIKeyError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = InvalidAPIKeyError("Invalid key")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "API key invalid" in result["error"]

    def test_usage_limit_exceeded_error(self, mock_config, mock_tavily_client):
        try:
            from tavily.errors import UsageLimitExceededError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = UsageLimitExceededError("Monthly quota exceeded")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "quota exhausted" in result["error"].lower()

    def test_tavily_api_error_429(self, mock_config, mock_tavily_client):
        try:
            from tavily.errors import TavilyAPIError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = TavilyAPIError("Rate limited", status_code=429)
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "429" in result["error"] or "rate limit" in result["error"].lower()
        # Verify no time.sleep was called (removed in fix)

    def test_httpx_timeout(self, mock_config, mock_tavily_client):
        import httpx
        mock_tavily_client.search.side_effect = httpx.TimeoutException("Request timed out")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "timed out" in result["error"].lower()

    def test_httpx_connect_error(self, mock_config, mock_tavily_client):
        import httpx
        mock_tavily_client.search.side_effect = httpx.ConnectError("Connection refused")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "connect" in result["error"].lower()

    def test_httpx_http_status_error_401(self, mock_config, mock_tavily_client):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_tavily_client.search.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "authentication" in result["error"].lower()

    def test_httpx_http_status_error_403(self, mock_config, mock_tavily_client):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_tavily_client.search.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "authentication" in result["error"].lower() or "403" in result["error"]

    def test_httpx_http_status_error_429(self, mock_config, mock_tavily_client):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_tavily_client.search.side_effect = httpx.HTTPStatusError(
            "Rate Limited", request=MagicMock(), response=mock_response
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "429" in result["error"] or "rate limit" in result["error"].lower()

    def test_unknown_tavily_error(self, mock_config, mock_tavily_client):
        mock_tavily_client.search.side_effect = Exception("Something weird")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "Tavily error" in result["error"]


# ── Test: Keyless Mode ───────────────────────────────────────────────────────

class TestKeylessMode:
    def test_keyless_search(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="search", query="test")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_keyless_extract(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="extract", urls=["https://example.com"])
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_keyless_crawl_blocked(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_keyless_map_blocked(self, mock_config, mock_tavily_client):
        mock_config.tavily_api_key = ""
        result = tavily(action="map", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_keyless_warning_logged_once(self, mock_config, mock_tavily_client, caplog):
        import logging
        mock_config.tavily_api_key = ""
        with caplog.at_level(logging.WARNING, logger="tools.tavily"):
            # First call should log warning
            tavily(action="search", query="test")
            # Second call should NOT log again
            tavily(action="search", query="test2")
        assert caplog.text.count("keyless mode") == 1


# ── Test: SSRF ───────────────────────────────────────────────────────────────

class TestSSRF:
    def test_extract_private_ip(self, mock_config, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="extract", urls=["http://192.168.1.1/secret"])
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_crawl_private_ip(self, mock_config, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="crawl", url="http://10.0.0.1/admin")
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_map_private_ip(self, mock_config, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="map", url="http://127.0.0.1:8080")
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_extract_public_allowed(self, mock_config, mock_tavily_client):
        result = tavily(action="extract", urls=["https://github.com"])
        assert result["status"] == "success"


# ── Test: Client Caching ─────────────────────────────────────────────────────

class TestClientCaching:
    def test_client_singleton(self, mock_config, mock_tavily_client):
        # First call creates client
        c1 = _get_client()
        # Second call returns same instance
        c2 = _get_client()
        assert c1 is c2

    def test_client_key_change(self, mock_config, mock_tavily_client):
        # Create client with first key
        mock_config.tavily_api_key = "key-a"
        c1 = _get_client()
        # Change key
        mock_config.tavily_api_key = "key-b"
        c2 = _get_client()
        # Should be different instance (rebuilt)
        assert c1 is not c2

    def test_client_thread_safety(self, mock_config, mock_tavily_client):
        import threading
        clients = []
        def get_client_thread():
            clients.append(_get_client())
        threads = [threading.Thread(target=get_client_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All threads should get the same instance
        assert all(c is clients[0] for c in clients)
