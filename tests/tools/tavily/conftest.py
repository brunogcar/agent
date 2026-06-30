"""Shared fixtures for tavily tests."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _async_return(value):
    """Create a real async function that returns value.

    v1.1: Used as side_effect for MagicMock to avoid AsyncMock GC warnings
    while preserving call_args, assert_called_once, etc.
    """
    async def _inner(*args, **kwargs):
        return value
    return _inner


@pytest.fixture(autouse=True)
def reset_tavily_state():
    """Reset Tavily client singleton and circuit breaker before each test."""
    import tools.tavily_ops.state as state
    from tools.tavily_ops.client import _TAVILY_CB
    state.reset_state()
    _TAVILY_CB._state = "closed"
    _TAVILY_CB._failure_count = 0
    _TAVILY_CB._last_failure_time = 0.0
    _TAVILY_CB._half_open_calls = 0
    yield
    state.reset_state()
    _TAVILY_CB._state = "closed"
    _TAVILY_CB._failure_count = 0
    _TAVILY_CB._last_failure_time = 0.0
    _TAVILY_CB._half_open_calls = 0


@pytest.fixture(autouse=True)
def mock_cfg_for_tavily():
    """Mock cfg to prevent real API calls."""
    with patch("tools.tavily_ops.client.cfg") as mock_cfg:
        mock_cfg.tavily_api_key = "tvly-test-key-123"
        mock_cfg.tavily_timeout = 60
        with patch("tools.tavily_ops.errors.cfg", mock_cfg):
            yield mock_cfg


@pytest.fixture
def mock_tavily_client():
    """Return a mock AsyncTavilyClient with awaitable async methods.

    v1.1: Uses MagicMock with side_effect=_async_return(...) instead of
    AsyncMock to avoid 'coroutine never awaited' warnings while preserving
    call_args, assert_called_once, and side_effect override capability.
    """
    client = MagicMock()
    client.search = MagicMock(side_effect=_async_return({
        "results": [
            {"url": "https://example.com", "title": "Example", "content": "Hello"}
        ],
        "answer": "Test answer",
    }))
    client.extract = MagicMock(side_effect=_async_return({
        "results": [{"url": "https://example.com", "raw_content": "Extracted text"}]
    }))
    client.crawl = MagicMock(side_effect=_async_return({
        "results": [{"url": "https://example.com/page1", "title": "Page 1"}]
    }))
    client.map = MagicMock(side_effect=_async_return({
        "results": [{"url": "https://example.com/sitemap", "title": "Sitemap"}]
    }))
    client.research = MagicMock(side_effect=_async_return({
        "answer": "Research answer",
        "citations": [{"url": "https://example.com", "title": "Cite"}],
    }))
    with patch("tools.tavily_ops.client._get_singleton_client", return_value=client):
        yield client
