# tests/core/router/test_router_drift.py
"""CI check: router prompt tool list must match the actual registry.

This test detects drift between the hardcoded tool list in the router
system prompt and the tools actually registered via @tool decorator.
It does NOT change runtime behavior — it only fails CI when someone
adds a tool but forgets to update the router prompt.

If this test fails:
1. Add the new tool name to the router system prompt in core/router/router.py
2. OR add it to _ROUTER_EXCLUDED_TOOLS if it should never be routed to
"""
from __future__ import annotations
import re
import pytest
from unittest.mock import patch

# Tools that exist in the registry but should NOT appear in the router prompt
# because they are internal-only or not meant for user-facing routing.
_ROUTER_EXCLUDED_TOOLS = frozenset({
    # Add internal tools here as needed, e.g.:
    # "internal_health_check",
})


def _extract_tools_from_router_prompt() -> set[str]:
    """Parse tool names from the router system prompt string."""
    from core.router import TaskRouter

    router = TaskRouter()
    import inspect
    source = inspect.getsource(router._model_route)

    # Find the tool list in the system prompt
    # Pattern: "tool": "word or word or word"
    match = re.search(r'"tool"\s*:\s*"([^"]+)"', source)
    if not match:
        pytest.fail("Could not find tool list in router system prompt")

    tool_str = match.group(1)
    tools = {t.strip() for t in tool_str.split(" or ")}
    return tools


def test_router_tool_list_matches_registry():
    """Router prompt must mention all user-facing registered tools."""
    # Mock get_tool_names to return a known set of registered tools.
    # In production, get_tool_names() is populated during server boot
    # when register_all_tools() scans the codebase. In tests, we mock
    # to avoid importing the full registry (which requires FastMCP).
    mock_registered = {
        "web", "python", "file", "git", "vision",
        "memory", "agent", "notify", "report", "workflow",
    }

    with patch("registry.get_tool_names", return_value=list(mock_registered)):
        from registry import get_tool_names
        registered = set(get_tool_names())

    mentioned = _extract_tools_from_router_prompt()

    # Filter out excluded tools
    relevant_registered = registered - _ROUTER_EXCLUDED_TOOLS

    missing_from_prompt = relevant_registered - mentioned
    extra_in_prompt = mentioned - relevant_registered

    if missing_from_prompt or extra_in_prompt:
        msg_parts = []
        if missing_from_prompt:
            msg_parts.append(f"Missing from router prompt: {sorted(missing_from_prompt)}")
        if extra_in_prompt:
            msg_parts.append(f"Extra in router prompt (not registered): {sorted(extra_in_prompt)}")
        pytest.fail("Router prompt is out of sync with registry.\n" + "\n".join(msg_parts))
