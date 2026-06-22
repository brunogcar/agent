"""tests/core/router/test_router_drift.py
CI check: router prompt tool list and workflow list must match the expected set.

This test detects drift between the hardcoded tool/workflow lists in the router
system prompt and the expected user-facing set. It does NOT change runtime
behavior — it only fails CI when someone adds a tool/workflow but forgets to
update the router prompt.

If this test fails:
1. Add the new tool/workflow name to the router system prompt in core/router.py
2. Update _ROUTER_EXPECTED_TOOLS and _ROUTER_EXPECTED_WORKFLOWS below
3. Update conftest.py mock_registry fixture
4. Update docs/core/ROUTER.md

[ROUTER EXPANSION] This file was updated to use a hardcoded expected set
(Option B) rather than real registry discovery, keeping tests fast and
deterministic with no import side effects.
"""
from __future__ import annotations
import re
import pytest

# [ROUTER EXPANSION] Source of truth for the expected user-facing routable set.
# These must stay in sync with the router prompt in core/router.py.
# When adding a new tool or workflow, update ALL of these sets.
_ROUTER_EXPECTED_TOOLS = frozenset({
    "web", "python", "file", "git", "memory",
    "agent", "notify", "report", "vision", "workflow",
    "cli", "browser", "tavily", "consult", "parallel",
})
_ROUTER_EXPECTED_WORKFLOWS = frozenset({
    "research", "data", "autocode", "deep_research", "understand",
})

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


def _extract_workflows_from_router_prompt() -> set[str]:
    """Parse workflow names from the router system prompt string."""
    from core.router import TaskRouter

    router = TaskRouter()
    import inspect
    source = inspect.getsource(router._model_route)

    match = re.search(r'"workflow"\s*:\s*"([^"]+)"', source)
    if not match:
        pytest.fail("Could not find workflow list in router system prompt")

    wf_str = match.group(1)
    workflows = {w.strip() for w in wf_str.split(" or ")}
    return workflows


def test_router_tool_list_matches_expected():
    """Router prompt must mention all expected tools and no extras."""
    mentioned = _extract_tools_from_router_prompt()

    missing_from_prompt = _ROUTER_EXPECTED_TOOLS - mentioned
    extra_in_prompt = mentioned - _ROUTER_EXPECTED_TOOLS

    if missing_from_prompt or extra_in_prompt:
        msg_parts = []
        if missing_from_prompt:
            msg_parts.append(f"Missing from router prompt: {sorted(missing_from_prompt)}")
        if extra_in_prompt:
            msg_parts.append(f"Extra in router prompt (not expected): {sorted(extra_in_prompt)}")
        pytest.fail("Router prompt tool list is out of sync.\n" + "\n".join(msg_parts))


def test_router_workflow_list_matches_expected():
    """Router prompt must mention all expected workflows and no extras."""
    mentioned = _extract_workflows_from_router_prompt()

    missing_from_prompt = _ROUTER_EXPECTED_WORKFLOWS - mentioned
    extra_in_prompt = mentioned - _ROUTER_EXPECTED_WORKFLOWS

    if missing_from_prompt or extra_in_prompt:
        msg_parts = []
        if missing_from_prompt:
            msg_parts.append(f"Missing from router prompt: {sorted(missing_from_prompt)}")
        if extra_in_prompt:
            msg_parts.append(f"Extra in router prompt (not expected): {sorted(extra_in_prompt)}")
        pytest.fail("Router prompt workflow list is out of sync.\n" + "\n".join(msg_parts))


def test_router_tool_count_is_15():
    """Explicit count check to catch silent additions/removals."""
    mentioned = _extract_tools_from_router_prompt()
    assert len(mentioned) == 15, (
        f"Expected exactly 15 tools in prompt, found {len(mentioned)}: {sorted(mentioned)}"
    )


def test_router_workflow_count_is_5():
    """Explicit count check to catch silent additions/removals."""
    mentioned = _extract_workflows_from_router_prompt()
    assert len(mentioned) == 5, (
        f"Expected exactly 5 workflows in prompt, found {len(mentioned)}: {sorted(mentioned)}"
    )
