"""
tests/tools/tavily/test_tavily.py
Comprehensive tests for the Tavily research tool.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tools.tavily import tavily


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture(autouse=True)
def reset_tavily_client():
    """Reset the lazy client between tests."""
    import tools.tavily

    tools.tavily._tavily_client = None
    yield
    tools.tavily._tavily_client = None


@pytest.fixture
def mock_config():
    """Mock configuration for tavily tool with explicit integers."""
    with patch("tools.tavily.cfg") as mock_cfg:
        mock_cfg.tavily_api_key = "tvly-test-key"
        mock_cfg.tavily_timeout = 60
        mock_cfg.web_max_text_chars = 8000
        yield mock_cfg


@pytest.fixture
def mock_keyless_config():
    """Mock configuration for keyless mode."""
    with patch("tools.tavily.cfg") as mock_cfg:
        mock_cfg.tavily_api_key = ""
        mock_cfg.tavily_timeout = 60
        mock_cfg.web_max_text_chars = 8000
        yield mock_cfg


@pytest.fixture
def mock_tavily_client():
    """Mock Tavily client by patching _get_client (no tavily package needed)."""
    with patch("tools.tavily._get_client") as mock_get_client:
        client = AsyncMock()
        mock_get_client.return_value = client
        yield client


# =============================================================================
# Test Search
# =============================================================================
class TestSearch:
    def test_search_success(self, mock_config, mock_tavily_client):
        mock_tavily_client.search.return_value = {
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Test",
                    "content": "Content",
                }
            ],
            "answer": "AI answer",
        }
        result = tavily(action="search", query="test query")
        assert result["status"] == "success"
        assert result["data"]["answer"] == "AI answer"
        assert len(result["data"]["results"]) == 1
        assert result["data"]["keyless"] is False

    def test_search_missing_query(self, mock_config):
        result = tavily(action="search", query="")
        assert result["status"] == "error"
        assert "query is required" in result["error"]

    def test_search_keyless_caps_results(self, mock_keyless_config, mock_tavily_client):
        mock_tavily_client.search.return_value = {"results": []}
        result = tavily(action="search", query="test", max_results=10)
        assert result["status"] == "success"
        # Verify it was capped to 3
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["max_results"] == 3

    def test_search_strips_raw_content_by_default(self, mock_config, mock_tavily_client):
        mock_tavily_client.search.return_value = {
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Test",
                    "content": "Content",
                    "raw_content": "Very long text...",
                }
            ],
        }
        result = tavily(action="search", query="test")
        assert "raw_content" not in result["data"]["results"][0]

    def test_search_includes_raw_content_when_requested(
        self, mock_config, mock_tavily_client
    ):
        mock_tavily_client.search.return_value = {
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Test",
                    "content": "Content",
                    "raw_content": "Very long text...",
                }
            ],
        }
        result = tavily(action="search", query="test", include_raw_content=True)
        assert "raw_content" in result["data"]["results"][0]

    def test_search_error_handling(self, mock_config, mock_tavily_client):
        mock_tavily_client.search.side_effect = Exception("Network error")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "Network error" in result["error"]


# =============================================================================
# Test Extract
# =============================================================================
class TestExtract:
    def test_extract_success(self, mock_config, mock_tavily_client):
        mock_tavily_client.extract.return_value = {
            "results": [
                {"url": "https://example.com", "text": "Extracted content"}
            ]
        }
        result = tavily(action="extract", urls=["https://example.com"])
        assert result["status"] == "success"
        assert len(result["data"]["results"]) == 1

    def test_extract_missing_urls(self, mock_config):
        result = tavily(action="extract", urls=None)
        assert result["status"] == "error"
        assert "urls is required" in result["error"]

    def test_extract_too_many_urls(self, mock_config):
        result = tavily(action="extract", urls=["https://example.com"] * 11)
        assert result["status"] == "error"
        assert "cannot exceed 10" in result["error"]

    def test_extract_ssrf_blocks_private(self, mock_config, mock_tavily_client):
        result = tavily(action="extract", urls=["http://192.168.1.1/admin"])
        assert result["status"] == "error"
        assert "Blocked" in result["error"]


# =============================================================================
# Test Crawl
# =============================================================================
class TestCrawl:
    def test_crawl_success(self, mock_config, mock_tavily_client):
        mock_tavily_client.crawl.return_value = {
            "results": [{"url": "https://example.com/page1"}]
        }
        result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "success"

    def test_crawl_keyless_fails(self, mock_keyless_config):
        result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_crawl_missing_url(self, mock_config):
        result = tavily(action="crawl", url="")
        assert result["status"] == "error"
        assert "url or query is required" in result["error"]


# =============================================================================
# Test Map
# =============================================================================
class TestMap:
    def test_map_success(self, mock_config, mock_tavily_client):
        mock_tavily_client.map.return_value = {
            "results": [{"url": "https://example.com/page1"}]
        }
        result = tavily(action="map", url="https://example.com")
        assert result["status"] == "success"

    def test_map_keyless_fails(self, mock_keyless_config):
        result = tavily(action="map", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]


# =============================================================================
# Test Error Handling
# =============================================================================
class TestErrorHandling:
    def test_unknown_action(self, mock_config):
        result = tavily(action="unknown")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_tavily_keyless_limit_error(self, mock_keyless_config, mock_tavily_client):
        try:
            from tavily.errors import TavilyKeylessLimitError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = TavilyKeylessLimitError(
            "Limit reached"
        )
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "keyless rate limit" in result["error"].lower()

    def test_tavily_invalid_key_error(self, mock_config, mock_tavily_client):
        try:
            from tavily.errors import InvalidAPIKeyError
        except ImportError:
            pytest.skip("tavily-python not installed")
        mock_tavily_client.search.side_effect = InvalidAPIKeyError("Invalid key")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "invalid" in result["error"].lower()

    def test_httpx_timeout(self, mock_config, mock_tavily_client):
        import httpx

        mock_tavily_client.search.side_effect = httpx.TimeoutException("Timeout")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "timed out" in result["error"].lower()

    def test_httpx_connect_error(self, mock_config, mock_tavily_client):
        import httpx

        mock_tavily_client.search.side_effect = httpx.ConnectError("No connection")
        result = tavily(action="search", query="test")
        assert result["status"] == "error"
        assert "connect" in result["error"].lower()
