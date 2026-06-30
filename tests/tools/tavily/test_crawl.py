"""Tavily tests — crawl action."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestCrawl:
    """Test tavily crawl action."""

    def test_crawl_success(self, mock_tavily_client):
        result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is False
        mock_tavily_client.crawl.assert_called_once()

    def test_crawl_missing_url(self, mock_tavily_client):
        result = tavily(action="crawl")
        assert result["status"] == "error"
        # v1.1: Updated to match new error message (url is now strictly required)
        assert "action='crawl' requires url=" in result["error"]

    # v1.1: REMOVED test_crawl_uses_query_as_url_fallback — this behavior was
    # a bug. query is now purely for instructions, not a URL substitute.
    # Passing only query without url returns an error.

    def test_crawl_query_as_instructions(self, mock_tavily_client):
        """v1.1: query is passed as instructions, not as URL fallback."""
        result = tavily(action="crawl", url="https://example.com", query="find API docs")
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.crawl.call_args[1]
        assert call_kwargs["instructions"] == "find API docs"
        assert call_kwargs["url"] == "https://example.com"

    def test_crawl_keyless_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_crawl_ssrf_blocked(self, mock_tavily_client):
        # v1.1: Patch core.security.is_safe_network_address since
        # _assert_safe_urls was moved there for cross-tool sharing.
        with patch("core.security.is_safe_network_address", return_value=False):
            result = tavily(action="crawl", url="http://192.168.1.1/admin")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_crawl_passes_extract_depth_and_format(self, mock_tavily_client):
        result = tavily(
            action="crawl",
            url="https://example.com",
            extract_depth="advanced",
            format="text",
        )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.crawl.call_args[1]
        assert call_kwargs["extract_depth"] == "advanced"
        assert call_kwargs["format"] == "text"

    def test_crawl_uses_instructions_not_query(self, mock_tavily_client):
        result = tavily(action="crawl", url="https://example.com", query="find API docs")
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.crawl.call_args[1]
        assert call_kwargs["instructions"] == "find API docs"
        assert "query" not in call_kwargs
