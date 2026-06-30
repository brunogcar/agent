"""Tavily tests — SSRF guard."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestSSRF:
    """Test SSRF protection across URL-touching actions."""

    def test_extract_blocks_private_ip(self, mock_tavily_client):
        # v1.1: Patch core.security.is_safe_network_address
        with patch("core.security.is_safe_network_address", return_value=False):
            result = tavily(action="extract", urls=["http://127.0.0.1/secret"])
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_crawl_blocks_private_ip(self, mock_tavily_client):
        # v1.1: Patch core.security.is_safe_network_address
        with patch("core.security.is_safe_network_address", return_value=False):
            result = tavily(action="crawl", url="http://192.168.1.1/admin")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_map_blocks_private_ip(self, mock_tavily_client):
        # v1.1: Patch core.security.is_safe_network_address
        with patch("core.security.is_safe_network_address", return_value=False):
            result = tavily(action="map", url="http://10.0.0.1/internal")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_search_does_not_check_ssrf(self, mock_tavily_client):
        """Search does not fetch arbitrary URLs — no SSRF check needed."""
        result = tavily(action="search", query="test")
        assert result["status"] == "success"
