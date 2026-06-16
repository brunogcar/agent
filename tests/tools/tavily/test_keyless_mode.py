"""Tavily tool tests — keyless mode.

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


class TestKeylessMode:
    """Test tavily keyless mode behavior."""

    def test_keyless_search(self, mock_tavily_client):
        from tools import tavily as tavily_mod
        original_key = tavily_mod.cfg.tavily_api_key
        tavily_mod.cfg.tavily_api_key = ""
        try:
            result = tavily(action="search", query="test")
            assert result["status"] == "success"
            assert result["data"]["keyless"] is True
        finally:
            tavily_mod.cfg.tavily_api_key = original_key

    def test_keyless_extract(self, mock_tavily_client):
        from tools import tavily as tavily_mod
        original_key = tavily_mod.cfg.tavily_api_key
        tavily_mod.cfg.tavily_api_key = ""
        try:
            result = tavily(action="extract", urls=["https://example.com"])
            assert result["status"] == "success"
            assert result["data"]["keyless"] is True
        finally:
            tavily_mod.cfg.tavily_api_key = original_key

    def test_keyless_crawl_blocked(self, mock_tavily_client):
        from tools import tavily as tavily_mod
        original_key = tavily_mod.cfg.tavily_api_key
        tavily_mod.cfg.tavily_api_key = ""
        try:
            result = tavily(action="crawl", url="https://example.com")
            assert result["status"] == "error"
            assert "requires a Tavily API key" in result["error"]
        finally:
            tavily_mod.cfg.tavily_api_key = original_key

    def test_keyless_map_blocked(self, mock_tavily_client):
        from tools import tavily as tavily_mod
        original_key = tavily_mod.cfg.tavily_api_key
        tavily_mod.cfg.tavily_api_key = ""
        try:
            result = tavily(action="map", url="https://example.com")
            assert result["status"] == "error"
            assert "requires a Tavily API key" in result["error"]
        finally:
            tavily_mod.cfg.tavily_api_key = original_key

    def test_keyless_warning_logged_once(self, mock_tavily_client, caplog):
        import logging
        from tools import tavily as tavily_mod
        original_key = tavily_mod.cfg.tavily_api_key
        tavily_mod.cfg.tavily_api_key = ""
        try:
            with caplog.at_level(logging.WARNING, logger="tools.tavily"):
                tavily(action="search", query="test")
                tavily(action="search", query="test2")
            assert caplog.text.count("keyless mode") == 1
        finally:
            tavily_mod.cfg.tavily_api_key = original_key
