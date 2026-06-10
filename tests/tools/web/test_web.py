"""
tests/tools/web/test_web.py
Comprehensive unit tests for the web tool, focusing on:
- P2: URL deduplication in search_and_read
- Search functionality
- Scraping functionality
- SSRF protection
- Error handling
"""
import pytest
from unittest.mock import patch, MagicMock
import httpx

from tools.web import web, _do_search, _do_scrape, _is_safe_url


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def mock_config():
    """Mock configuration for web tool with explicit integer values."""
    with patch("tools.web.cfg") as mock_cfg:
        # CRITICAL: Set actual integers to avoid MagicMock comparison errors
        mock_cfg.web_max_text_chars = 8000
        mock_cfg.web_snippet_chars = 300
        mock_cfg.web_max_search_results = 10
        mock_cfg.searxng_url = "http://localhost:8080"
        yield mock_cfg


@pytest.fixture
def mock_httpx():
    """Mock httpx.Client for network isolation."""
    with patch("tools.web._make_client") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value.__enter__.return_value = client_instance
        yield client_instance


# =============================================================================
# Test URL Deduplication (P2 Fix)
# =============================================================================
class TestURLDeduplication:
    def test_search_and_read_removes_duplicates(self, mock_config, mock_httpx):
        """Test that duplicate URLs from different engines are deduplicated."""
        # Note: search_and_read caps search results at 3 (n = min(max_results, 3))
        search_response = MagicMock()
        search_response.json.return_value = {
            "results": [
                {"url": "https://example.com/page1", "title": "Page 1", "content": "Snippet 1", "engine": "google"},
                {"url": "https://example.com/page2", "title": "Page 2", "content": "Snippet 2", "engine": "bing"},
                {"url": "https://example.com/page1", "title": "Page 1 Dup", "content": "Snippet 1 dup", "engine": "duckduckgo"},
            ]
        }
        search_response.raise_for_status = MagicMock()

        scrape_response = MagicMock()
        scrape_response.text = "<html><body>Test content</body></html>"
        scrape_response.raise_for_status = MagicMock()

        # 1 search call + 2 scrape calls (since page1 is deduplicated)
        mock_httpx.get.side_effect = [search_response, scrape_response, scrape_response]

        result = web(action="search_and_read", query="test query", max_results=3)

        assert result["status"] == "success"
        assert result["data"]["attempted"] == 2  # Only 2 unique URLs
        assert result["data"]["duplicates_removed"] == 1
        assert len(result["data"]["results"]) == 2

    def test_search_and_read_preserves_order(self, mock_config, mock_httpx):
        """Test that URL order is preserved after deduplication."""
        search_response = MagicMock()
        search_response.json.return_value = {
            "results": [
                {"url": "https://example.com/first", "title": "First", "content": "First snippet", "engine": "google"},
                {"url": "https://example.com/second", "title": "Second", "content": "Second snippet", "engine": "bing"},
                {"url": "https://example.com/first", "title": "First Dup", "content": "First dup", "engine": "duckduckgo"},
            ]
        }
        search_response.raise_for_status = MagicMock()

        scrape_response = MagicMock()
        scrape_response.text = "<html><body>Content</body></html>"
        scrape_response.raise_for_status = MagicMock()

        # 1 search call + 2 scrape calls
        mock_httpx.get.side_effect = [search_response, scrape_response, scrape_response]

        result = web(action="search_and_read", query="test", max_results=3)

        assert result["status"] == "success"
        # Check order is preserved (first, second - the duplicate 'first' is dropped)
        urls = [r["url"] for r in result["data"]["results"]]
        assert urls == [
            "https://example.com/first",
            "https://example.com/second",
        ]

    def test_search_and_read_all_duplicates(self, mock_config, mock_httpx):
        """Test handling when all search results are the same URL."""
        search_response = MagicMock()
        search_response.json.return_value = {
            "results": [
                {"url": "https://example.com/same", "title": "Same 1", "content": "Snippet", "engine": "google"},
                {"url": "https://example.com/same", "title": "Same 2", "content": "Snippet", "engine": "bing"},
                {"url": "https://example.com/same", "title": "Same 3", "content": "Snippet", "engine": "duckduckgo"},
            ]
        }
        search_response.raise_for_status = MagicMock()

        scrape_response = MagicMock()
        scrape_response.text = "<html><body>Content</body></html>"
        scrape_response.raise_for_status = MagicMock()

        # 1 search call + 1 scrape call
        mock_httpx.get.side_effect = [search_response, scrape_response]

        result = web(action="search_and_read", query="test", max_results=3)

        assert result["status"] == "success"
        assert result["data"]["attempted"] == 1
        assert result["data"]["duplicates_removed"] == 2


# =============================================================================
# Test Search Functionality
# =============================================================================
class TestSearch:
    def test_search_success(self, mock_config, mock_httpx):
        """Test successful search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"url": "https://example.com", "title": "Example", "content": "Test snippet", "engine": "google"}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        result = web(action="search", query="test query")

        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert result["data"]["results"][0]["url"] == "https://example.com"

    def test_search_missing_query(self, mock_config):
        """Test search without query parameter."""
        result = web(action="search", query="")

        assert result["status"] == "error"
        assert "requires query" in result["error"]

    def test_search_timeout(self, mock_config, mock_httpx):
        """Test search timeout handling."""
        mock_httpx.get.side_effect = httpx.TimeoutException("Timeout")

        result = web(action="search", query="test")

        assert result["status"] == "error"
        assert "timeout" in result["error"].lower()

    def test_search_connection_error(self, mock_config, mock_httpx):
        """Test search connection error."""
        mock_httpx.get.side_effect = httpx.ConnectError("Connection failed")

        result = web(action="search", query="test")

        assert result["status"] == "error"
        assert "Cannot reach" in result["error"]


# =============================================================================
# Test Scrape Functionality
# =============================================================================
class TestScrape:
    def test_scrape_success(self, mock_config, mock_httpx):
        """Test successful scrape."""
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        result = web(action="scrape", url="https://example.com")

        assert result["status"] == "success"
        assert result["data"]["title"] == "Test"
        assert "Content" in result["data"]["text"]

    def test_scrape_missing_url(self, mock_config):
        """Test scrape without URL parameter."""
        result = web(action="scrape", url="")

        assert result["status"] == "error"
        assert "requires url" in result["error"]

    def test_read_alias(self, mock_config, mock_httpx):
        """Test that 'read' is an alias for 'scrape'."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        result = web(action="read", url="https://example.com")

        assert result["status"] == "success"


# =============================================================================
# Test SSRF Protection
# =============================================================================
class TestSSRFProtection:
    def test_blocks_localhost(self, mock_config, mock_httpx, monkeypatch):
        """Test that localhost URLs are blocked."""
        import tools.vision
        monkeypatch.setattr(tools.vision.cfg, "allowed_internal_hosts", frozenset())
        result = web(action="scrape", url="http://localhost:8080/admin")

        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_blocks_private_ip(self, mock_config, mock_httpx):
        """Test that private IP addresses are blocked."""
        result = web(action="scrape", url="http://192.168.1.1/config")

        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_allows_public_url(self, mock_config, mock_httpx):
        """Test that public URLs are allowed."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Public content</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        # Patch _is_safe_url to return True for this test
        with patch("tools.web._is_safe_url", return_value=True):
            result = web(action="scrape", url="https://example.com")

        assert result["status"] == "success"


# =============================================================================
# Test Error Handling
# =============================================================================
class TestErrorHandling:
    def test_unknown_action(self, mock_config):
        """Test unknown action returns error."""
        result = web(action="unknown_action")

        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_search_and_read_no_results(self, mock_config, mock_httpx):
        """Test search_and_read with no search results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        result = web(action="search_and_read", query="no results query")

        assert result["status"] == "error"
        assert "No search results" in result["error"]

    def test_scrape_http_error(self, mock_config, mock_httpx):
        """Test scrape with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        mock_httpx.get.side_effect = error

        with patch("tools.web._is_safe_url", return_value=True):
            result = web(action="scrape", url="https://example.com/notfound")

        assert result["status"] == "error"
        assert "404" in result["error"]


# =============================================================================
# Test Helper Functions
# =============================================================================
class TestHelperFunctions:
    def test_is_safe_url_blocks_loopback(self, monkeypatch):
        """Test _is_safe_url blocks loopback addresses."""
        import tools.vision
        monkeypatch.setattr(tools.vision.cfg, "allowed_internal_hosts", frozenset())
        assert _is_safe_url("http://127.0.0.1/admin") is False
        assert _is_safe_url("http://localhost/admin") is False

    def test_is_safe_url_blocks_private(self):
        """Test _is_safe_url blocks private networks."""
        assert _is_safe_url("http://192.168.1.1") is False
        assert _is_safe_url("http://10.0.0.1") is False
        assert _is_safe_url("http://172.16.0.1") is False

    def test_is_safe_url_invalid_hostname(self):
        """Test _is_safe_url handles invalid hostnames."""
        assert _is_safe_url("not-a-url") is False
        assert _is_safe_url("") is False