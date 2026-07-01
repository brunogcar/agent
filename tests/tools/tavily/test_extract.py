"""Tests for tools/tavily_ops/actions/extract.py.

v1.3: Fixed SSRF tests to patch _assert_safe_urls explicitly.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tools.tavily import tavily


class TestExtract:
    """Tests for the extract action."""

    def test_extract_success(self, mock_tavily_client):
        with patch("tools.tavily_ops.actions.extract._assert_safe_urls", return_value=""):
            result = tavily(
                action="extract",
                urls=["https://example.com", "https://github.com"],
            )
            assert result["status"] == "success"
            assert "results" in result["data"]

    def test_extract_missing_urls(self):
        result = tavily(action="extract")
        assert result["status"] == "error"
        assert "urls is required" in result["error"]

    def test_extract_too_many_urls(self):
        urls = [f"https://example{i}.com" for i in range(11)]
        result = tavily(action="extract", urls=urls)
        assert result["status"] == "error"
        assert "cannot exceed" in result["error"]

    def test_extract_ssrf_blocked(self):
        """SSRF blocked for private IPs in URL list."""
        with patch(
            "tools.tavily_ops.actions.extract._assert_safe_urls",
            return_value="Blocked: http://127.0.0.1/secret",
        ):
            result = tavily(
                action="extract",
                urls=["https://example.com", "http://127.0.0.1/secret"],
            )
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_extract_keyless(self, mock_tavily_client):
        """v1.3 FIX: Patch module-level _is_keyless, not mock method."""
        with patch("tools.tavily_ops.client._is_keyless", return_value=True):
            with patch("tools.tavily_ops.actions.extract._assert_safe_urls", return_value=""):
                result = tavily(action="extract", urls=["https://example.com"])
                assert result["status"] == "success"
                assert result["data"]["keyless"] is True
