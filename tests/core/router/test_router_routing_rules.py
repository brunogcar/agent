"""tests/core/router/test_router_routing_rules.py
Parameterized validation: every tool and workflow in the router prompt
has a corresponding routing rule description.

These tests parse the prompt text and verify descriptive coverage.
No LLM mocking required.
"""
from __future__ import annotations

import ast
import inspect
import re

import pytest

from core.router import TaskRouter


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


# [ROUTER EXPANSION] Each tool must have a routing rule line in the prompt.
# Format expected: "- tool_name: description"
ROUTER_TOOLS = [
    "web", "python", "file", "git", "memory",
    "agent", "notify", "report", "vision", "workflow",
    "cli", "browser", "tavily", "consult", "parallel",
]

# [ROUTER EXPANSION] Each workflow must have a routing rule line in the prompt.
ROUTER_WORKFLOWS = [
    "research", "data", "autocode", "deep_research", "understand",
]


class TestToolRoutingRules:
    """Every tool in the prompt has a descriptive routing rule."""

    @pytest.mark.parametrize("tool_name", ROUTER_TOOLS)
    def test_tool_has_routing_rule(self, tool_name: str):
        prompt = _extract_prompt_section()
        # Look for a line like: "- web: general web search..."
        # Match: start of line, optional whitespace, dash, space, tool_name, colon, space, word char
        pattern = rf"^\s*-\s*{re.escape(tool_name)}\s*:\s*\w"
        if not re.search(pattern, prompt, re.MULTILINE):
            pytest.fail(
                f"Tool '{tool_name}' is listed in the prompt but has no "
                f"routing rule description (expected line: '- {tool_name}: ...')"
            )


class TestWorkflowRoutingRules:
    """Every workflow in the prompt has a descriptive routing rule."""

    @pytest.mark.parametrize("workflow_name", ROUTER_WORKFLOWS)
    def test_workflow_has_routing_rule(self, workflow_name: str):
        prompt = _extract_prompt_section()
        pattern = rf"^\s*-\s*{re.escape(workflow_name)}\s*:\s*\w"
        if not re.search(pattern, prompt, re.MULTILINE):
            pytest.fail(
                f"Workflow '{workflow_name}' is listed in the prompt but has no "
                f"routing rule description (expected line: '- {workflow_name}: ...')"
            )


class TestPromptSectionsPresent:
    """Verify the prompt has the expected structural sections."""

    def test_workflow_routing_rules_section(self):
        prompt = _extract_prompt_section()
        assert "Workflow routing rules:" in prompt, (
            "Missing 'Workflow routing rules:' section in prompt"
        )

    def test_tool_routing_rules_section(self):
        prompt = _extract_prompt_section()
        assert "Tool routing rules (for direct workflow):" in prompt, (
            "Missing 'Tool routing rules' section in prompt"
        )

    def test_confidence_rules_section(self):
        prompt = _extract_prompt_section()
        assert "Confidence rules:" in prompt, (
            "Missing 'Confidence rules:' section in prompt"
        )
