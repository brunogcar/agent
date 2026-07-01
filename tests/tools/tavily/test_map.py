"""Tavily tests — map action.

v1.2: Added facade params and coroutine factory tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestMap:
    """Test tavily map action."""

    def test_map_success(self, mock_tavily_client):
        with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
            result = tavily(action="map", url="https://example.com")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        mock_tavily_client.map.assert_called_once()

    def test_map_missing_url(self, mock_tavily_client):
        result = tavily(action="map")
        assert result["status"] == "error"
        assert "action='map' requires url=" in result["error"]

    def test_map_keyless_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
                result = tavily(action="map", url="https://example.com")
            assert result["status"] == "error"
            assert "requires a Tavily API key" in result["error"]

    def test_map_ssrf_blocked(self, mock_tavily_client):
        result = tavily(action="map", url="http://192.168.1.1/secret")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    # v1.2: NEW — facade params
    def test_map_facade_params(self, mock_tavily_client):
        with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
            result = tavily(
                action="map",
                url="https://example.com",
                max_depth=5,
                max_breadth=20,
                limit=100,
            )
        assert result["status"] == "success"
        call_kwargs = mock_tavily_client.map.call_args[1]
        assert call_kwargs["max_depth"] == 5
        assert call_kwargs["max_breadth"] == 20
        assert call_kwargs["limit"] == 100
