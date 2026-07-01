"""Tavily tests — keyless mode behavior.

v1.2: Fixed tests to work with _assert_safe_urls mock.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily
from tools.tavily_ops import state


class TestKeylessMode:
    """Test keyless mode behavior."""

    def test_keyless_search(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="search", query="test")
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True

    def test_keyless_extract(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
                result = tavily(action="extract", urls=["https://example.com"])
            assert result["status"] == "success"
            assert result["data"]["keyless"] is True

    def test_keyless_crawl_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
                result = tavily(action="crawl", url="https://example.com")
            assert result["status"] == "error"
            assert "requires a Tavily API key" in result["error"]

    def test_keyless_map_blocked(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
                result = tavily(action="map", url="https://example.com")
            assert result["status"] == "error"
            assert "requires a Tavily API key" in result["error"]

    def test_keyless_warning_logged_once(self, caplog, mock_tavily_client):
        """Keyless warning should be logged exactly once."""
        # v1.2 FIX: Reset _KEYLESS_WARNED before test
        from tools.tavily_ops import client as client_module
        client_module._KEYLESS_WARNED = False

        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with caplog.at_level("WARNING"):
                result = tavily(action="search", query="test")

        assert result["status"] == "success"
        assert "keyless mode" in caplog.text.lower()
        assert caplog.text.count("keyless mode") == 1
