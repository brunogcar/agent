"""tests/core/router/test_router_routing_rules.py
Parameterized validation: every tool and workflow in the router prompt
has a corresponding routing rule description.

These tests use the module-level ROUTER_SYSTEM_PROMPT constant directly.
No source parsing or LLM mocking required.
"""
from __future__ import annotations

import re

import pytest

from core.router import ROUTER_SYSTEM_PROMPT
from tests.core.router.conftest import (
    ROUTER_EXPECTED_TOOLS,
    ROUTER_EXPECTED_WORKFLOWS,
)

class TestToolRoutingRules:
    """Every tool in the prompt has a descriptive routing rule."""

    @pytest.mark.parametrize("tool_name", sorted(ROUTER_EXPECTED_TOOLS))
    def test_tool_has_routing_rule(self, tool_name: str):
        # Look for a line like: "- web: general web search..."
        pattern = rf"^\s*-\s*{re.escape(tool_name)}\s*:\s*."
        if not re.search(pattern, ROUTER_SYSTEM_PROMPT, re.MULTILINE):
            pytest.fail(
                f"Tool '{tool_name}' is listed in the prompt but has no "
                f"routing rule description (expected line: '- {tool_name}: ...')"
            )

class TestWorkflowRoutingRules:
    """Every workflow in the prompt has a descriptive routing rule."""

    @pytest.mark.parametrize("workflow_name", sorted(ROUTER_EXPECTED_WORKFLOWS))
    def test_workflow_has_routing_rule(self, workflow_name: str):
        pattern = rf"^\s*-\s*{re.escape(workflow_name)}\s*:\s*."
        if not re.search(pattern, ROUTER_SYSTEM_PROMPT, re.MULTILINE):
            pytest.fail(
                f"Workflow '{workflow_name}' is listed in the prompt but has no "
                f"routing rule description (expected line: '- {workflow_name}: ...')"
            )

class TestPromptSectionsPresent:
    """Verify the prompt has the expected structural sections."""

    def test_workflow_routing_rules_section(self):
        assert "Workflow routing rules:" in ROUTER_SYSTEM_PROMPT, (
            "Missing 'Workflow routing rules:' section in prompt"
        )

    def test_tool_routing_rules_section(self):
        assert "Tool routing rules (for direct workflow):" in ROUTER_SYSTEM_PROMPT, (
            "Missing 'Tool routing rules' section in prompt"
        )

    def test_confidence_rules_section(self):
        assert "Confidence rules:" in ROUTER_SYSTEM_PROMPT, (
            "Missing 'Confidence rules:' section in prompt"
        )

    # [ROUTER FIX v2] Verify few-shot examples section exists
    def test_examples_section_present(self):
        assert "Examples:" in ROUTER_SYSTEM_PROMPT, (
            "Missing 'Examples:' section in router system prompt"
        )
