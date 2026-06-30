"""Tavily tests — keyless mode."""
from __future__ import annotations

import logging
import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestKeylessMode:
    """Test tavily keyless mode behavior."""

    def test_keyless_search(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="search", query="test")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_keyless_extract(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="extract", urls=["https://example.com"])
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_keyless_crawl_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_keyless_map_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="map", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_keyless_warning_logged_once(self, mock_tavily_client, caplog):
        import tools.tavily_ops.state as state
        with caplog.at_level(logging.WARNING, logger="tools.tavily_ops.client"):
            with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
                tavily(action="search", query="test")
                tavily(action="search", query="test2")
        assert caplog.text.count("keyless mode") == 1
