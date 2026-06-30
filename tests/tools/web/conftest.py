"""Shared fixtures for web tool tests.

All web infrastructure is fully mocked; no real HTTP requests are made.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_web_state():
    """Reset all web module globals before each test."""
    from tools.web_ops import state as web_state
    web_state.reset_state()
    yield
    web_state.reset_state()


@pytest.fixture(autouse=True)
def mock_cfg_for_web(tmp_path):
    """Mock cfg to prevent AsyncMock leakage and provide web defaults."""
    with (
        patch("tools.web_ops.actions.search.cfg") as mock_cfg_search,
        patch("tools.web_ops.actions.scrape.cfg") as mock_cfg_scrape,
        patch("tools.web_ops.actions.search_and_read.cfg") as mock_cfg_sar,
    ):
        for mock_cfg in (mock_cfg_search, mock_cfg_scrape, mock_cfg_sar):
            mock_cfg.web_max_text_chars = 8000
            mock_cfg.web_snippet_chars = 300
            mock_cfg.web_max_search_results = 10
            mock_cfg.searxng_url = "http://localhost:8080"
            mock_cfg.worker_timeout = 60
        yield mock_cfg_sar


@pytest.fixture
def mock_httpx():
    """Mock the singleton httpx client, returning a mock client instance."""
    client_instance = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=client_instance)
    ctx.__exit__ = MagicMock(return_value=False)

    patch_paths = [
        "tools.web_ops.actions.search._make_client",
        "tools.web_ops.actions.scrape._make_client",
    ]
    patches = [patch(p, return_value=ctx) for p in patch_paths]
    for p in patches:
        p.start()
    try:
        yield client_instance
    finally:
        for p in patches:
            p.stop()
