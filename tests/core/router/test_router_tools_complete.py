"""tests/core/router/test_router_tools_complete.py
Structural completeness tests: verify the router prompt mentions
all expected tools and workflows.

These tests parse the router source code (not the LLM) to ensure
the prompt string is complete. They require no mocked LLM calls.
"""
from __future__ import annotations

import ast
import inspect
import re

import pytest

from core.router import TaskRouter

# [ROUTER EXPANSION] Source of truth for expected routable entities.
# When adding a new tool or workflow, update these sets AND the router prompt.
_EXPECTED_TOOLS = {
    "web", "python", "file", "git", "memory",
    "agent", "notify", "report", "vision", "workflow",
    "cli", "browser", "tavily", "consult", "parallel",
}
_EXPECTED_WORKFLOWS = {
    "research", "data", "autocode", "deep_research", "understand",
}


def _extract_prompt_from_source(source_text: str) -> str:
    """Extract the system prompt string content from _model_route source.

    Parses the Python string concatenation inside system=(...) and returns
    the actual string content with escape sequences decoded.
    """
    match = re.search(
        r"system\s*=\s*\((.*?)\),\s*\n\s*user\s*=",
        source_text, re.DOTALL
    )
    if not match:
        raise ValueError("Could not find system prompt block")

    block = match.group(1)

    # Extract all string literals from the block and decode them.
    # We use ast.literal_eval to safely parse Python string literals.
    contents = []

    # Double-quoted strings (handling escaped quotes and newlines)
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', block):
        try:
            contents.append(ast.literal_eval('"' + m.group(1) + '"'))
        except (ValueError, SyntaxError):
            pass

    # Single-quoted strings (handling escaped quotes and newlines)
    for m in re.finditer(r"'((?:[^'\\]|\\.)*)'", block):
        try:
            contents.append(ast.literal_eval("'" + m.group(1) + "'"))
        except (ValueError, SyntaxError):
            pass

    return "".join(contents)


def _extract_prompt_section() -> str:
    """Return the full system prompt string from _model_route source."""
    router = TaskRouter()
    source = inspect.getsource(router._model_route)
    return _extract_prompt_from_source(source)


class TestToolListComplete:
    """Verify every expected tool appears in the router system prompt."""

    def test_all_tools_mentioned_in_prompt(self):
        prompt = _extract_prompt_section()
        # Find the tool list: "tool": "web or python or ..."
        match = re.search(r'"tool"\s*:\s*"([^"]+)"', prompt)
        if not match:
            pytest.fail("Could not find tool list in router system prompt")

        tool_str = match.group(1)
        mentioned = {t.strip() for t in tool_str.split(" or ")}

        missing = _EXPECTED_TOOLS - mentioned
        extra = mentioned - _EXPECTED_TOOLS

        errors = []
        if missing:
            errors.append(f"Missing from prompt tool list: {sorted(missing)}")
        if extra:
            errors.append(f"Extra in prompt tool list (not expected): {sorted(extra)}")
        if errors:
            pytest.fail("Router prompt tool list incomplete.\n" + "\n".join(errors))

    def test_tool_count_matches_expected(self):
        prompt = _extract_prompt_section()
        match = re.search(r'"tool"\s*:\s*"([^"]+)"', prompt)
        tool_str = match.group(1)
        mentioned = {t.strip() for t in tool_str.split(" or ")}
        assert len(mentioned) == len(_EXPECTED_TOOLS), (
            f"Expected {len(_EXPECTED_TOOLS)} tools, found {len(mentioned)}. "
            f"Difference: {sorted(mentioned.symmetric_difference(_EXPECTED_TOOLS))}"
        )


class TestWorkflowListComplete:
    """Verify every expected workflow appears in the router system prompt."""

    def test_all_workflows_mentioned_in_prompt(self):
        prompt = _extract_prompt_section()
        match = re.search(r'"workflow"\s*:\s*"([^"]+)"', prompt)
        if not match:
            pytest.fail("Could not find workflow list in router system prompt")

        wf_str = match.group(1)
        mentioned = {w.strip() for w in wf_str.split(" or ")}

        missing = _EXPECTED_WORKFLOWS - mentioned
        extra = mentioned - _EXPECTED_WORKFLOWS

        errors = []
        if missing:
            errors.append(f"Missing from prompt workflow list: {sorted(missing)}")
        if extra:
            errors.append(f"Extra in prompt workflow list (not expected): {sorted(extra)}")
        if errors:
            pytest.fail("Router prompt workflow list incomplete.\n" + "\n".join(errors))

    def test_workflow_count_matches_expected(self):
        prompt = _extract_prompt_section()
        match = re.search(r'"workflow"\s*:\s*"([^"]+)"', prompt)
        wf_str = match.group(1)
        mentioned = {w.strip() for w in wf_str.split(" or ")}
        assert len(mentioned) == len(_EXPECTED_WORKFLOWS), (
            f"Expected {len(_EXPECTED_WORKFLOWS)} workflows, found {len(mentioned)}. "
            f"Difference: {sorted(mentioned.symmetric_difference(_EXPECTED_WORKFLOWS))}"
        )


class TestRoutingDecisionDataclass:
    """Tests migrated from the old monolithic test_router.py.
    Verify RoutingDecision defaults and custom values.
    """

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
