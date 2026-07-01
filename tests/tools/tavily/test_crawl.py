"""Tavily tests — crawl action.

v1.2: Added coroutine factory verification.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestCrawl:
    """Test tavily crawl action."""

    def test_crawl_success(self, mock_tavily_client):
        with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
            result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        mock_tavily_client.crawl.assert_called_once()

    def test_crawl_missing_url(self, mock_tavily_client):
        result = tavily(action="crawl")
        assert result["status"] == "error"
        assert "action='crawl' requires url=" in result["error"]

    def test_crawl_query_as_instructions(self, mock_tavily_client):
        with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
            result = tavily(
                action="crawl",
                url="https://example.com",
                query="focus on asyncio",
            )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.crawl.call_args[1]
        assert call_kwargs["instructions"] == "focus on asyncio"

    def test_crawl_keyless_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
                result = tavily(action="crawl", url="https://example.com")
            assert result["status"] == "error"
            assert "requires a Tavily API key" in result["error"]

    def test_crawl_ssrf_blocked(self, mock_tavily_client):
        result = tavily(action="crawl", url="http://127.0.0.1/admin")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    # v1.2: NEW — facade params pass-through
    def test_crawl_facade_params(self, mock_tavily_client):
        with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
            result = tavily(
                action="crawl",
                url="https://example.com",
                max_depth=5,
                max_breadth=20,
                limit=100,
            )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.crawl.call_args[1]
        assert call_kwargs["max_depth"] == 5
        assert call_kwargs["max_breadth"] == 20
        assert call_kwargs["limit"] == 100

    # v1.2: NEW — coroutine factory pattern
    def test_crawl_uses_coroutine_factory(self, mock_tavily_client):
        """Crawl action passes factory to _run_async_with_resilience."""
        call_count = [0]

        async def _side_effect(*args, **kwargs):
            call_count[0] += 1
            return {"results": [{"url": "https://example.com/page1"}]}

        mock_tavily_client.crawl.side_effect = _side_effect

        with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
            with patch("tools.tavily_ops.bridge.time.sleep"):
                result = tavily(action="crawl", url="https://example.com")

        assert result["status"] == "success"
        assert call_count[0] == 1  # Factory called once on success
