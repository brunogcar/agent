"""Tavily tests — extract action.

v1.2: Added consistency tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily


class TestExtract:
    """Test tavily extract action."""

    def test_extract_success(self, mock_tavily_client):
        with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
            result = tavily(
                action="extract",
                urls=["https://example.com"],
            )
        assert result["status"] == "success"
        mock_tavily_client.extract.assert_called_once()

    def test_extract_missing_urls(self, mock_tavily_client):
        result = tavily(action="extract")
        assert result["status"] == "error"
        assert "urls is required" in result["error"]

    def test_extract_too_many_urls(self, mock_tavily_client):
        urls = [f"https://example{i}.com" for i in range(15)]
        result = tavily(action="extract", urls=urls)
        assert result["status"] == "error"
        assert "cannot exceed 10" in result["error"]

    def test_extract_ssrf_blocked(self, mock_tavily_client):
        result = tavily(
            action="extract",
            urls=["https://example.com", "http://127.0.0.1/secret"],
        )
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_extract_keyless_mode(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.errors._assert_safe_urls", return_value=""):
                result = tavily(action="extract", urls=["https://example.com"])
            assert result["status"] == "success"
            assert result["data"]["keyless"] is True
