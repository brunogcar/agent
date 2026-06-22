"""tests/core/router/test_router_tools_complete.py
Structural completeness tests: verify the router prompt mentions
all expected tools and workflows.

These tests use the module-level ROUTER_SYSTEM_PROMPT constant directly.
No source parsing or mocked LLM calls required.
"""
from __future__ import annotations

import re

import pytest

from core.router import ROUTER_SYSTEM_PROMPT
from tests.core.router.conftest import (
    ROUTER_EXPECTED_TOOLS,
    ROUTER_EXPECTED_WORKFLOWS,
)


class TestToolListComplete:
    """Verify every expected tool appears in the router system prompt."""

    def test_all_tools_mentioned_in_prompt(self):
        match = re.search(r'"tool"\s*:\s*"([^"]+)"', ROUTER_SYSTEM_PROMPT)
        if not match:
            pytest.fail("Could not find tool list in router system prompt")

        tool_str = match.group(1)
        mentioned = {t.strip() for t in tool_str.split(" or ")}

        missing = ROUTER_EXPECTED_TOOLS - mentioned
        extra = mentioned - ROUTER_EXPECTED_TOOLS

        errors = []
        if missing:
            errors.append(f"Missing from prompt tool list: {sorted(missing)}")
        if extra:
            errors.append(f"Extra in prompt tool list (not expected): {sorted(extra)}")
        if errors:
            pytest.fail("Router prompt tool list incomplete.\n" + "\n".join(errors))

    def test_tool_count_matches_expected(self):
        match = re.search(r'"tool"\s*:\s*"([^"]+)"', ROUTER_SYSTEM_PROMPT)
        tool_str = match.group(1)
        mentioned = {t.strip() for t in tool_str.split(" or ")}
        assert len(mentioned) == len(ROUTER_EXPECTED_TOOLS), (
            f"Expected {len(ROUTER_EXPECTED_TOOLS)} tools, found {len(mentioned)}. "
            f"Difference: {sorted(mentioned.symmetric_difference(ROUTER_EXPECTED_TOOLS))}"
        )


class TestWorkflowListComplete:
    """Verify every expected workflow appears in the router system prompt."""

    def test_all_workflows_mentioned_in_prompt(self):
        match = re.search(r'"workflow"\s*:\s*"([^"]+)"', ROUTER_SYSTEM_PROMPT)
        if not match:
            pytest.fail("Could not find workflow list in router system prompt")

        wf_str = match.group(1)
        mentioned = {w.strip() for w in wf_str.split(" or ")}

        missing = ROUTER_EXPECTED_WORKFLOWS - mentioned
        extra = mentioned - ROUTER_EXPECTED_WORKFLOWS

        errors = []
        if missing:
            errors.append(f"Missing from prompt workflow list: {sorted(missing)}")
        if extra:
            errors.append(f"Extra in prompt workflow list (not expected): {sorted(extra)}")
        if errors:
            pytest.fail("Router prompt workflow list incomplete.\n" + "\n".join(errors))

    def test_workflow_count_matches_expected(self):
        match = re.search(r'"workflow"\s*:\s*"([^"]+)"', ROUTER_SYSTEM_PROMPT)
        wf_str = match.group(1)
        mentioned = {w.strip() for w in wf_str.split(" or ")}
        assert len(mentioned) == len(ROUTER_EXPECTED_WORKFLOWS), (
            f"Expected {len(ROUTER_EXPECTED_WORKFLOWS)} workflows, found {len(mentioned)}. "
            f"Difference: {sorted(mentioned.symmetric_difference(ROUTER_EXPECTED_WORKFLOWS))}"
        )


class TestRoutingDecisionDataclass:
    """Verify RoutingDecision defaults and custom values."""

    def test_default_values(self):
        from core.router import RoutingDecision
        raw = {}
        decision = RoutingDecision(raw)
        assert decision.workflow == "research"
        assert decision.tool == "web"
        assert decision.complexity == 5
        assert decision.confidence == "medium"
        assert decision.clarifying_questions == []

    def test_custom_values_with_questions(self):
        from core.router import RoutingDecision
        raw = {
            "workflow": "autocode",
            "tool": "workflow",
            "complexity": 8,
            "reason": "Code fix",
            "confidence": "low",
            "clarifying_questions": ["Which file?", "What is the error?"]
        }
        decision = RoutingDecision(raw)
        assert decision.workflow == "autocode"
        assert decision.complexity == 8
        assert decision.confidence == "low"
        assert len(decision.clarifying_questions) == 2
