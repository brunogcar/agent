"""Tavily tests — search action."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestSearch:
    """Test tavily search action."""

    def test_search_success(self, mock_tavily_client):
        result = tavily(action="search", query="pytest testing")
        assert result["status"] == "success"
        # v1.1: answer is now included in response data
        assert result["data"]["answer"] == "Test answer"
        assert len(result["data"]["results"]) == 1
        mock_tavily_client.search.assert_called_once()

    def test_search_missing_query(self, mock_tavily_client):
        result = tavily(action="search")
        assert result["status"] == "error"
        # v1.1: Updated to match new error message
        assert "action='search' requires query=" in result["error"]

    def test_search_keyless_mode(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="search", query="test")
        assert result["status"] == "success"
        # v1.1: keyless flag is now included in response data
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
        # trace_id is threaded through ok() and prune_tool_dict()
        assert result.get("trace_id") == "trace-123"

    # v1.1: NEW — verify include_domains/exclude_domains pass-through
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

    # v1.1: NEW — verify topic pass-through
    def test_search_topic(self, mock_tavily_client):
        result = tavily(
            action="search",
            query="stock market today",
            topic="finance",
        )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["topic"] == "finance"

    # v1.1: NEW — verify max_results validation rejects out-of-range values
    def test_search_max_results_too_high(self, mock_tavily_client):
        result = tavily(action="search", query="test", max_results=100)
        assert result["status"] == "error"
        assert "max_results must be <= 20" in result["error"]

    def test_search_max_results_zero(self, mock_tavily_client):
        result = tavily(action="search", query="test", max_results=0)
        assert result["status"] == "error"
        assert "max_results must be >= 1" in result["error"]

    # v1.1: NEW — verify include_images is passed to SDK
    def test_search_include_images(self, mock_tavily_client):
        result = tavily(action="search", query="test", include_images=True)
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.search.call_args[1]
        assert call_kwargs["include_images"] is True
