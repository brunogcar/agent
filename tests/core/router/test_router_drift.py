"""tests/core/router/test_router_drift.py
CI check: router prompt tool list and workflow list must match the expected set.

This test detects drift between the hardcoded tool/workflow lists in the router
system prompt and the expected user-facing set. It does NOT change runtime
behavior -- it only fails CI when someone adds a tool/workflow but forgets to
update the router prompt.

If this test fails:
1. Add the new tool/workflow name to the router system prompt in core/router.py
2. Update ROUTER_EXPECTED_TOOLS and ROUTER_EXPECTED_WORKFLOWS in conftest.py
3. Update docs/core/ROUTER.md

[ROUTER FIX] This file now imports canonical constants from conftest.py
and uses the module-level ROUTER_SYSTEM_PROMPT directly.
"""
from __future__ import annotations

import pytest

from tests.core.router.conftest import (
    ROUTER_EXPECTED_TOOLS,
    ROUTER_EXPECTED_WORKFLOWS,
    extract_tools_from_router_prompt,
    extract_workflows_from_router_prompt,
)


def test_router_tool_list_matches_expected():
    """Router prompt must mention all expected tools and no extras."""
    mentioned = extract_tools_from_router_prompt()

    missing_from_prompt = ROUTER_EXPECTED_TOOLS - mentioned
    extra_in_prompt = mentioned - ROUTER_EXPECTED_TOOLS

    if missing_from_prompt or extra_in_prompt:
        msg_parts = []
        if missing_from_prompt:
            msg_parts.append(f"Missing from router prompt: {sorted(missing_from_prompt)}")
        if extra_in_prompt:
            msg_parts.append(f"Extra in router prompt (not expected): {sorted(extra_in_prompt)}")
        pytest.fail("Router prompt tool list is out of sync.\n" + "\n".join(msg_parts))


def test_router_workflow_list_matches_expected():
    """Router prompt must mention all expected workflows and no extras."""
    mentioned = extract_workflows_from_router_prompt()

    missing_from_prompt = ROUTER_EXPECTED_WORKFLOWS - mentioned
    extra_in_prompt = mentioned - ROUTER_EXPECTED_WORKFLOWS

    if missing_from_prompt or extra_in_prompt:
        msg_parts = []
        if missing_from_prompt:
            msg_parts.append(f"Missing from router prompt: {sorted(missing_from_prompt)}")
        if extra_in_prompt:
            msg_parts.append(f"Extra in router prompt (not expected): {sorted(extra_in_prompt)}")
        pytest.fail("Router prompt workflow list is out of sync.\n" + "\n".join(msg_parts))


def test_router_tool_count_is_15():
    """Explicit count check to catch silent additions/removals."""
    mentioned = extract_tools_from_router_prompt()
    assert len(mentioned) == 15, (
        f"Expected exactly 15 tools in prompt, found {len(mentioned)}: {sorted(mentioned)}"
    )


def test_router_workflow_count_is_5():
    """Explicit count check to catch silent additions/removals."""
    mentioned = extract_workflows_from_router_prompt()
    assert len(mentioned) == 5, (
        f"Expected exactly 5 workflows in prompt, found {len(mentioned)}: {sorted(mentioned)}"
    )
