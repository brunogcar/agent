"""Unit tests for web search_and_read action with URL deduplication."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.web import web


class TestURLDeduplication:
    def test_search_and_read_removes_duplicates(self, mock_cfg_for_web, mock_httpx):
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
        mock_httpx.get.side_effect = [search_response, scrape_response, scrape_response]
        with patch("core.memory_backend.pruner.prune_tool_dict") as mock_prune:
            mock_prune.return_value = {"status": "success", "data": {"pruned": True}}
            result = web(action="search_and_read", query="test query", max_results=3, max_chars=8000)
        assert result["status"] == "success"
        mock_prune.assert_called_once()
        call_args = mock_prune.call_args
        assert call_args[0][0] == "web"
        pruned_data = call_args[0][1]
        assert pruned_data["data"]["attempted"] == 2
        assert pruned_data["data"]["duplicates_removed"] == 1

    def test_search_and_read_preserves_order(self, mock_cfg_for_web, mock_httpx):
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
        mock_httpx.get.side_effect = [search_response, scrape_response, scrape_response]
        with patch("core.memory_backend.pruner.prune_tool_dict") as mock_prune:
            mock_prune.return_value = {"status": "success", "data": {"pruned": True}}
            result = web(action="search_and_read", query="test", max_results=3, max_chars=8000)
        assert result["status"] == "success"
        call_args = mock_prune.call_args
        pruned_data = call_args[0][1]
        urls = [r["url"] for r in pruned_data["data"]["results"]]
        assert urls == [
            "https://example.com/first",
            "https://example.com/second",
        ]

    def test_search_and_read_all_duplicates(self, mock_cfg_for_web, mock_httpx):
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
        mock_httpx.get.side_effect = [search_response, scrape_response]
        with patch("core.memory_backend.pruner.prune_tool_dict") as mock_prune:
            mock_prune.return_value = {"status": "success", "data": {"pruned": True}}
            result = web(action="search_and_read", query="test", max_results=3, max_chars=8000)
        assert result["status"] == "success"
        call_args = mock_prune.call_args
        pruned_data = call_args[0][1]
        assert pruned_data["data"]["attempted"] == 1
        assert pruned_data["data"]["duplicates_removed"] == 2
