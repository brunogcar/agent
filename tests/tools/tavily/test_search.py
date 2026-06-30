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
        assert result["data"]["answer"] == "Test answer"
        assert len(result["data"]["results"]) == 1
        mock_tavily_client.search.assert_called_once()

    def test_search_missing_query(self, mock_tavily_client):
        result = tavily(action="search")
        assert result["status"] == "error"
        assert "query is required" in result["error"]

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
        # trace_id is threaded through ok() and prune_tool_dict()
        assert result.get("trace_id") == "trace-123"
