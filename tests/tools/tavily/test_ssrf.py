"""Tavily tool tests — SSRF protection.

[BUGFIX-SECURITY] Fully mocked; no real Tavily API calls.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tools.tavily import tavily, _get_client, _handle_tavily_error


# ── Shared fixtures (each file is self-contained) ───────────────────────────

@pytest.fixture(autouse=True)
def reset_tavily_state():
    """Reset Tavily client singleton before each test."""
    from tools import tavily as tavily_mod
    tavily_mod._tavily_client = None
    tavily_mod._tavily_client_key = None
    tavily_mod._keyless_warned = False
    yield
    tavily_mod._tavily_client = None
    tavily_mod._tavily_client_key = None
    tavily_mod._keyless_warned = False


@pytest.fixture(autouse=True)
def mock_cfg_for_tavily():
    """Mock cfg to prevent AsyncMock leakage and provide Tavily defaults."""
    with patch("tools.tavily.cfg") as mock_cfg:
        mock_cfg.tavily_api_key = "tvly-test-key-123"
        mock_cfg.tavily_timeout = 60
        # Prevent CLI/other cross-test bleed
        mock_cfg.cli_max_command_chars = 4096
        mock_cfg.cli_max_arguments = 50
        yield mock_cfg


@pytest.fixture
def mock_tavily_client():
    """Return a mock AsyncTavilyClient with awaitable async methods."""
    client = MagicMock()
    client.search = AsyncMock(return_value={
        "results": [
            {"url": "https://example.com", "title": "Example", "content": "Hello"}
        ],
        "answer": "Test answer",
    })
    client.extract = AsyncMock(return_value={
        "results": [{"url": "https://example.com", "raw_content": "Extracted text"}]
    })
    client.crawl = AsyncMock(return_value={
        "results": [{"url": "https://example.com/page1", "title": "Page 1"}]
    })
    client.map = AsyncMock(return_value={
        "results": [{"url": "https://example.com/sitemap", "title": "Sitemap"}]
    })
    with patch("tools.tavily._get_client", return_value=client):
        yield client


class TestSSRF:
    """Test tavily SSRF blocking."""

    def test_extract_private_ip(self, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="extract", urls=["http://192.168.1.1/secret"])
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_crawl_private_ip(self, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="crawl", url="http://10.0.0.1/admin")
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_map_private_ip(self, mock_tavily_client):
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="map", url="http://127.0.0.1:8080")
            assert result["status"] == "error"
            assert "Blocked" in result["error"]

    def test_extract_public_allowed(self, mock_tavily_client):
        result = tavily(action="extract", urls=["https://github.com"])
        assert result["status"] == "success"
