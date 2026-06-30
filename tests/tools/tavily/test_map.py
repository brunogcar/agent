"""Tavily tests — map action."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestMap:
    """Test tavily map action."""

    def test_map_success(self, mock_tavily_client):
        result = tavily(action="map", url="https://example.com")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is False
        mock_tavily_client.map.assert_called_once()

    def test_map_missing_url(self, mock_tavily_client):
        result = tavily(action="map")
        assert result["status"] == "error"
        assert "url or query is required" in result["error"]

    def test_map_uses_query_as_url_fallback(self, mock_tavily_client):
        result = tavily(action="map", query="https://example.com")
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.map.call_args[1]
        assert call_kwargs["url"] == "https://example.com"

    def test_map_keyless_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="map", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_map_ssrf_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.errors.is_safe_network_address", return_value=False):
            result = tavily(action="map", url="http://192.168.1.1/admin")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_map_uses_instructions_not_query(self, mock_tavily_client):
        result = tavily(action="map", url="https://example.com", query="find API docs")
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.map.call_args[1]
        assert call_kwargs["instructions"] == "find API docs"
        assert "query" not in call_kwargs
