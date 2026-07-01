"""Shared fixtures for Tavily tool tests."""
from __future__ import annotations

import warnings
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.tavily_ops.client import _TAVILY_CB


@pytest.fixture(autouse=True)
def reset_tavily_state():
    """Reset Tavily singleton state before each test."""
    from tools.tavily_ops import state
    from core.net.budget import _budget_tracker
    state.reset_state()
    _TAVILY_CB.reset()
    _budget_tracker._calls.clear()
    _budget_tracker._configs.clear()
    _budget_tracker._last_reset_date = __import__("datetime").date.today()
    yield
    state.reset_state()
    _TAVILY_CB.reset()
    _budget_tracker._calls.clear()
    _budget_tracker._configs.clear()


@pytest.fixture(autouse=True)
def filter_resource_warnings():
    """Suppress asyncio resource warnings on Windows."""
    warnings.filterwarnings("ignore", category=ResourceWarning)
    warnings.filterwarnings("ignore", message="unclosed transport", category=Warning)
    warnings.filterwarnings("ignore", message="unclosed <socket", category=Warning)
    yield


@pytest.fixture
def mock_tavily_client():
    """Mock AsyncTavilyClient for action tests.

    v1.3 FIX: Uses AsyncMock for async methods so _run_async_with_resilience
    gets actual coroutines, while tests can still use assert_called_once/call_args.
    Also patches cfg.tavily_api_key so _is_keyless_mode() returns False by default.
    """
    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value={
        "results": [{"title": "Test", "url": "https://example.com", "raw_content": "Full HTML"}],
        "answer": "Test answer",
    })
    mock_client.extract = AsyncMock(return_value={
        "results": [{"content": "Test content"}],
    })
    mock_client.crawl = AsyncMock(return_value={
        "results": [{"title": "Test", "url": "https://example.com"}],
    })
    mock_client.map = AsyncMock(return_value={
        "results": [{"url": "https://example.com"}],
    })
    mock_client.research = AsyncMock(return_value={
        "answer": "Research answer",
        "citations": [],
    })
    mock_client.close = MagicMock()

    with patch("tools.tavily_ops.client._get_singleton_client", return_value=mock_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "tvly-test-key"):
            yield mock_client
