"""tests/core/router/conftest.py -- Shared fixtures and helpers for router test suite.

All router tests use these fixtures to mock external dependencies
(LLM client, registry) without importing heavy runtime modules.
"""
from __future__ import annotations

import re

import pytest
from unittest.mock import patch, MagicMock

# [ROUTER FIX] Canonical expected sets -- single source of truth.
# When adding a new tool or workflow, update ONLY these two constants.
ROUTER_EXPECTED_TOOLS = frozenset({
    "web", "python", "file", "git", "memory",
    "agent", "notify", "report", "vision", "workflow",
    "cli", "browser", "tavily", "consult", "parallel",
    "swarm",
})
ROUTER_EXPECTED_WORKFLOWS = frozenset({
    "research", "data", "autocode", "deep_research", "understand",
})


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
        mock.return_value = list(ROUTER_EXPECTED_TOOLS)
        yield mock


@pytest.fixture
def force_heuristic(mock_llm):
    """Make the LLM call fail so _heuristic_route is always used."""
    mock_llm.complete.return_value = MagicMock(ok=False)


# [ROUTER FIX] Prompt extraction now uses the module-level constant directly
# instead of fragile inspect.getsource() + ast.literal_eval parsing.
def get_router_prompt() -> str:
    """Return the router system prompt string from the module-level constant."""
    from core.router import ROUTER_SYSTEM_PROMPT
    return ROUTER_SYSTEM_PROMPT


def extract_tools_from_router_prompt() -> set[str]:
    """Parse tool names from the router system prompt string."""
    prompt = get_router_prompt()
    match = re.search(r'"tool"\s*:\s*"([^"]+)"', prompt)
    if not match:
        pytest.fail("Could not find tool list in router system prompt")
    tool_str = match.group(1)
    return {t.strip() for t in tool_str.split(" or ")}


def extract_workflows_from_router_prompt() -> set[str]:
    """Parse workflow names from the router system prompt string."""
    prompt = get_router_prompt()
    match = re.search(r'"workflow"\s*:\s*"([^"]+)"', prompt)
    if not match:
        pytest.fail("Could not find workflow list in router system prompt")
    wf_str = match.group(1)
    return {w.strip() for w in wf_str.split(" or ")}
