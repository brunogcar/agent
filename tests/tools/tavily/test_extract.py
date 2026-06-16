"""Tavily tool tests — extract action.

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


class TestExtract:
    """Test tavily extract action."""

    def test_extract_success(self, mock_tavily_client):
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
        with patch("tools.tavily.is_safe_network_address", return_value=False):
            result = tavily(action="extract", urls=["http://127.0.0.1/secret"])
            assert result["status"] == "error"
            assert "Blocked" in result["error"]
