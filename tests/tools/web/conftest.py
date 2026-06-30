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
    """Mock cfg to prevent AsyncMock leakage and provide web defaults.

    Yields a single shared mock object patched into all action modules
    that import cfg directly. This ensures mutations (e.g., setting
    searxng_url) are visible to every handler.
    """
    cfg_mock = MagicMock()
    cfg_mock.web_max_text_chars = 8000
    cfg_mock.web_snippet_chars = 300
    cfg_mock.web_max_search_results = 10
    cfg_mock.searxng_url = "http://localhost:8080"
    cfg_mock.worker_timeout = 60
    with (
        patch("tools.web_ops.actions.search.cfg", cfg_mock),
        patch("tools.web_ops.actions.scrape.cfg", cfg_mock),
        patch("tools.web_ops.actions.search_and_read.cfg", cfg_mock),
    ):
        yield cfg_mock


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
