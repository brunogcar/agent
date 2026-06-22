"""tests/core/router/conftest.py — Shared fixtures for router test suite.

All router tests use these fixtures to mock external dependencies
(LLM client, registry) without importing heavy runtime modules.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_llm():
    """Mock the LLM client to prevent actual LM Studio calls during tests.

    Yields a MagicMock that replaces `core.router.llm`.
    Usage in tests:
        def test_something(mock_llm):
            mock_llm.complete.return_value = MagicMock(ok=True, text='{"workflow": "research"}')
    """
    with patch("core.router.llm") as mock:
        yield mock


@pytest.fixture
def mock_registry():
    """Mock registry.get_tool_names to return a controlled tool set.

    Prevents importing the full registry (which requires FastMCP)
    during router drift tests.
    """
    with patch("registry.get_tool_names") as mock:
        # [ROUTER EXPANSION] Expected full set of user-facing routable tools.
        # This must stay in sync with the router prompt tool list.
        mock.return_value = [
            "web", "python", "file", "git", "vision",
            "memory", "agent", "notify", "report", "workflow",
            "cli", "browser", "tavily", "consult", "parallel",
        ]
        yield mock
