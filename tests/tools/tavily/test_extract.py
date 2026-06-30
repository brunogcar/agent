"""Tavily tests — extract action."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestExtract:
    """Test tavily extract action."""

    def test_extract_success(self, mock_tavily_client):
        # v1.1: urls is now a facade param, passed through to handler
        result = tavily(
            action="extract",
            urls=["https://example.com"],
            include_raw_content=True,
        )
        assert result["status"] == "success"
        assert len(result["data"]["results"]) == 1
        mock_tavily_client.extract.assert_called_once()

    def test_extract_missing_urls(self, mock_tavily_client):
        result = tavily(action="extract")
        assert result["status"] == "error"
        assert "urls is required" in result["error"]

    def test_extract_too_many_urls(self, mock_tavily_client):
        result = tavily(action="extract", urls=["https://a.com"] * 11)
        assert result["status"] == "error"
        assert "cannot exceed 10 items" in result["error"]

    def test_extract_ssrf_blocked(self, mock_tavily_client):
        # v1.1: Patch core.security.is_safe_network_address
        with patch("core.security.is_safe_network_address", return_value=False):
            result = tavily(action="extract", urls=["http://127.0.0.1/secret"])
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_extract_keyless(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            result = tavily(action="extract", urls=["https://example.com"])
        assert result["status"] == "success"
        assert result["data"]["keyless"] is True
