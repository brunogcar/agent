"""Tests for tools/tavily_ops/actions/crawl.py.

v1.3: Fixed URL expectation (normalize_url adds trailing slash to root).
      Fixed SSRF tests to patch _assert_safe_urls explicitly.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tools.tavily import tavily


class TestCrawl:
    """Tests for the crawl action."""

    def test_crawl_success(self, mock_tavily_client):
        """Basic crawl returns results."""
        with patch("tools.tavily_ops.actions.crawl._assert_safe_urls", return_value=""):
            result = tavily(action="crawl", url="https://example.com")
            assert result["status"] == "success"
            # v1.3: normalize_url adds trailing slash to root URLs
            assert result["data"]["url"] == "https://example.com/"

    def test_crawl_missing_url(self):
        result = tavily(action="crawl")
        assert result["status"] == "error"
        assert "requires url" in result["error"]

    def test_crawl_with_query(self, mock_tavily_client):
        with patch("tools.tavily_ops.actions.crawl._assert_safe_urls", return_value=""):
            result = tavily(action="crawl", url="https://example.com", query="focus on asyncio")
            assert result["status"] == "success"
            assert result["data"]["query"] == "focus on asyncio"

    def test_crawl_with_limits(self, mock_tavily_client):
        with patch("tools.tavily_ops.actions.crawl._assert_safe_urls", return_value=""):
            result = tavily(
                action="crawl",
                url="https://example.com",
                max_depth=2,
                max_breadth=5,
                limit=20,
            )
            assert result["status"] == "success"

    def test_crawl_ssrf_blocked(self):
        """SSRF blocked for private IPs."""
        with patch(
            "tools.tavily_ops.actions.crawl._assert_safe_urls",
            return_value="Blocked: http://127.0.0.1/admin",
        ):
            result = tavily(action="crawl", url="http://127.0.0.1/admin")
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_crawl_keyless_requires_key(self, mock_tavily_client):
        """v1.3 FIX: Patch module-level _is_keyless_mode, not mock method."""
        with patch("tools.tavily_ops.client._is_keyless_mode", return_value=True):
            with patch("tools.tavily_ops.actions.crawl._assert_safe_urls", return_value=""):
                result = tavily(action="crawl", url="https://example.com")
                assert result["status"] == "error"
                assert "requires a Tavily API key" in result["error"]
