"""Tavily tests — search action.

v1.2: Added raw_content stripping test, facade param pass-through tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestSearch:
    """Test tavily search action."""

    def test_search_success(self, mock_tavily_client):
        result = tavily(action="search", query="pytest testing")
        assert result["status"] == "success"
        assert result["data"]["answer"] == "Test answer"
        assert len(result["data"]["results"]) == 1
        mock_tavily_client.search.assert_called_once()

    def test_search_missing_query(self, mock_tavily_client):
        result = tavily(action="search")
        assert result["status"] == "error"
        assert "action='search' requires query=" in result["error"]

    def test_search_keyless_mode(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="search", query="test")
            assert result["status"] == "success"
            assert result["data"]["keyless"] is True

    def test_search_keyless_cap(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="search", query="test", max_results=10)
            assert result["status"] == "success"
            call_kwargs = mock_tavily_client.search.call_args[1]
            assert call_kwargs["max_results"] == 3

    def test_search_trace_id_propagation(self, mock_tavily_client):
        result = tavily(action="search", query="test", trace_id="trace-123")
        assert result["status"] == "success"
        assert result.get("trace_id") == "trace-123"

    def test_search_include_domains(self, mock_tavily_client):
        result = tavily(
            action="search",
            query="python asyncio",
            include_domains=["github.com", "docs.python.org"],
        )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["include_domains"] == ["github.com", "docs.python.org"]

    def test_search_exclude_domains(self, mock_tavily_client):
        result = tavily(
            action="search",
            query="python asyncio",
            exclude_domains=["pinterest.com", "quora.com"],
        )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["exclude_domains"] == ["pinterest.com", "quora.com"]

    def test_search_topic(self, mock_tavily_client):
        result = tavily(
            action="search",
            query="stock market today",
            topic="finance",
        )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["topic"] == "finance"

    def test_search_max_results_too_high(self, mock_tavily_client):
        result = tavily(action="search", query="test", max_results=100)
        assert result["status"] == "error"
        assert "max_results must be <= 20" in result["error"]

    def test_search_max_results_zero(self, mock_tavily_client):
        result = tavily(action="search", query="test", max_results=0)
        assert result["status"] == "error"
        assert "max_results must be >= 1" in result["error"]

    def test_search_include_images(self, mock_tavily_client):
        result = tavily(action="search", query="test", include_images=True)
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["include_images"] is True

    # v1.2: NEW — raw_content stripping when include_raw_content=False
    def test_search_raw_content_stripped_when_false(self, mock_tavily_client):
        """When include_raw_content=False, raw_content is removed from results."""
        # Override mock to return results with raw_content
        async def _side_effect(*args, **kwargs):
            return {
                "results": [
                    {
                        "url": "https://example.com",
                        "title": "Example",
                        "content": "Summary",
                        "raw_content": "<html><body>Full HTML</body></html>",
                    }
                ],
                "answer": "Test answer",
            }

        mock_tavily_client.search.side_effect = _side_effect

        result = tavily(action="search", query="test", include_raw_content=False)
        assert result["status"] == "success"
        for r in result["data"]["results"]:
            assert "raw_content" not in r

    def test_search_raw_content_preserved_when_true(self, mock_tavily_client):
        """When include_raw_content=True, raw_content is kept in results."""
        async def _side_effect(*args, **kwargs):
            return {
                "results": [
                    {
                        "url": "https://example.com",
                        "title": "Example",
                        "content": "Summary",
                        "raw_content": "<html><body>Full HTML</body></html>",
                    }
                ],
                "answer": "Test answer",
            }

        mock_tavily_client.search.side_effect = _side_effect

        result = tavily(action="search", query="test", include_raw_content=True)
        assert result["status"] == "success"
        for r in result["data"]["results"]:
            assert "raw_content" in r

    # v1.2: NEW — facade params pass-through
    def test_search_facade_params_passed(self, mock_tavily_client):
        """max_depth, max_breadth, limit are passed through facade to action handler."""
        # These params are for crawl/map, but the facade should accept and pass them
        result = tavily(
            action="search",
            query="test",
            max_depth=5,
            max_breadth=20,
            limit=100,
        )
        assert result["status"] == "success"
