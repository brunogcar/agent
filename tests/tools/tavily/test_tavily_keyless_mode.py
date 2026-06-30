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
            # v1.1: Also patch errors.cfg so timeout messages use mock value
            with patch("tools.tavily_ops.errors.cfg.tavily_api_key", ""):
                result = tavily(action="search", query="test")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_keyless_extract(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors.cfg.tavily_api_key", ""):
                result = tavily(action="extract", urls=["https://example.com"])
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_keyless_crawl_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors.cfg.tavily_api_key", ""):
                result = tavily(action="crawl", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    def test_keyless_map_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors.cfg.tavily_api_key", ""):
                result = tavily(action="map", url="https://example.com")
        assert result["status"] == "error"
        assert "requires a Tavily API key" in result["error"]

    # v1.1: Use the actual logger name from client.py (__name__ = tools.tavily_ops.client)
    def test_keyless_warning_logged_once(self, mock_tavily_client, caplog):
        import tools.tavily_ops.state as state
        # Reset warning flag so the test can observe the log
        state._KEYLESS_WARNED = False
        with caplog.at_level(logging.WARNING, logger="tools.tavily_ops.client"):
            with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
                with patch("tools.tavily_ops.errors.cfg.tavily_api_key", ""):
                    tavily(action="search", query="test")
                    tavily(action="search", query="test2")
        # The warning should mention "keyless mode"
        assert "keyless mode" in caplog.text.lower()
