"""Unit tests for web search_and_read action with URL deduplication."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.web import web


@pytest.fixture
def mock_config():
    """Mock configuration for web tool."""
    with patch("tools.web.cfg") as mock_cfg:
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


class TestURLDeduplication:
    def test_search_and_read_removes_duplicates(self, mock_config, mock_httpx):
        """Test that duplicate URLs from different engines are deduplicated."""
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
