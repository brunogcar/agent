"""Shared fixtures for tavily tests."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture(autouse=True)
def reset_tavily_state():
    """Reset Tavily client singleton before each test."""
    import tools.tavily_ops.state as state
    state.reset_state()
    yield
    state.reset_state()


@pytest.fixture(autouse=True)
def mock_cfg_for_tavily():
    """Mock cfg to prevent AsyncMock leakage and provide Tavily defaults."""
    with patch("tools.tavily_ops.client.cfg") as mock_cfg:
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
    client.research = AsyncMock(return_value={
        "answer": "Research answer",
        "citations": [{"url": "https://example.com", "title": "Cite"}],
    })
    with patch("tools.tavily_ops.client._get_singleton_client", return_value=client):
        yield client
