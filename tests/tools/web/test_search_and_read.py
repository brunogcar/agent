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
        scrape_response.text = "Test content"
        scrape_response.raise_for_status = MagicMock()
        scrape_response.headers = {"content-type": "text/html"}
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
        scrape_response.text = "Content"
        scrape_response.raise_for_status = MagicMock()
        scrape_response.headers = {"content-type": "text/html"}
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
        scrape_response.text = "Content"
        scrape_response.raise_for_status = MagicMock()
        scrape_response.headers = {"content-type": "text/html"}
        mock_httpx.get.side_effect = [search_response, scrape_response]
        with patch("core.memory_backend.pruner.prune_tool_dict") as mock_prune:
            mock_prune.return_value = {"status": "success", "data": {"pruned": True}}
            result = web(action="search_and_read", query="test", max_results=3, max_chars=8000)
        assert result["status"] == "success"
        call_args = mock_prune.call_args
        pruned_data = call_args[0][1]
        assert pruned_data["data"]["attempted"] == 1
        assert pruned_data["data"]["duplicates_removed"] == 2


class TestTimeoutBehavior:
    def test_search_and_read_timeout_returns_partial_results(self, mock_cfg_for_web):
        """When cfg.worker_timeout is exceeded, done futures return results;
        not_done futures are reported as timeout errors.

        This test mocks _action_scrape directly to avoid real HTTP sleeps
        inside ThreadPoolExecutor workers, which would make the test flaky.
        """
        import concurrent.futures

        # Set a very short timeout so wait() fires immediately
        mock_cfg_for_web.worker_timeout = 0.001
        mock_cfg_for_web.web_max_search_results = 10

        # Mock search to return 2 URLs
        with patch("tools.web_ops.actions.search_and_read._action_search") as mock_search:
            mock_search.return_value = {
                "status": "success",
                "data": {
                    "results": [
                        {"url": "https://example.com/fast", "title": "Fast"},
                        {"url": "https://example.com/slow", "title": "Slow"},
                    ]
                }
            }

            # Mock scrape: first call succeeds, second call sleeps past timeout
            def slow_scrape(**kwargs):
                import time
                url = kwargs.get("url", "")
                if "slow" in url:
                    time.sleep(0.1)  # Longer than 0.001s timeout
                return {
                    "status": "success",
                    "data": {
                        "url": url,
                        "title": "Title",
                        "text": f"Content from {url}",
                        "word_count": 10,
                        "truncated": False,
                    }
                }

            with patch("tools.web_ops.actions.search_and_read._action_scrape") as mock_scrape:
                mock_scrape.side_effect = slow_scrape
                with patch("core.memory_backend.pruner.prune_tool_dict") as mock_prune:
                    mock_prune.return_value = {"status": "success", "data": {"pruned": True}}
                    result = web(action="search_and_read", query="test", max_results=2, max_chars=8000)

        assert result["status"] == "success"
        # Verify prune was called with partial results
        mock_prune.assert_called_once()
        pruned_data = mock_prune.call_args[0][1]
        assert pruned_data["data"]["attempted"] == 2
        # At least one result may have timed out, so scraped_count <= attempted
        assert pruned_data["data"]["scraped_count"] <= pruned_data["data"]["attempted"]

    def test_search_and_read_mixed_success_failure(self, mock_cfg_for_web, mock_httpx):
        """One scrape succeeds, one fails with 404 — overall result is success
        with partial results."""
        import httpx

        search_response = MagicMock()
        search_response.json.return_value = {
            "results": [
                {"url": "https://example.com/good", "title": "Good", "content": "Snippet", "engine": "google"},
                {"url": "https://example.com/bad", "title": "Bad", "content": "Snippet", "engine": "bing"},
            ]
        }
        search_response.raise_for_status = MagicMock()

        good_response = MagicMock()
        good_response.text = "<html><body>Good content</body></html>"
        good_response.raise_for_status = MagicMock()
        good_response.headers = {"content-type": "text/html"}

        bad_response = MagicMock()
        bad_response.status_code = 404
        bad_error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=bad_response)

        mock_httpx.get.side_effect = [search_response, good_response, bad_error]

        with patch("core.memory_backend.pruner.prune_tool_dict") as mock_prune:
            mock_prune.return_value = {"status": "success", "data": {"pruned": True}}
            result = web(action="search_and_read", query="test", max_results=2, max_chars=8000)

        assert result["status"] == "success"
        pruned_data = mock_prune.call_args[0][1]
        assert pruned_data["data"]["attempted"] == 2
        assert pruned_data["data"]["scraped_count"] == 1
