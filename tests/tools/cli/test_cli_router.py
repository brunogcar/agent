"""Tests for CLI router and executor escalation (Layer 3-4)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.cli_ops.router import _call_router, _build_router_system


class TestRouterSystemPrompt:
    """Tests for router system prompt generation."""

    def test_dynamic_tool_list(self, mock_cfg):
        """Router prompt should include current DISPATCH tool names."""
        prompt = _build_router_system()
        assert "Allowed tool_name values" in prompt
        # Should contain at least some known tools
        assert "file" in prompt or "git" in prompt

    def test_valid_json_structure(self, mock_cfg):
        """Prompt should reference valid JSON structure."""
        prompt = _build_router_system()
        assert '"route": "dispatch"' in prompt
        assert '"route": "escalate"' in prompt


class TestRouterCall:
    """Tests for _call_router function."""

    def test_dispatch_route(self, mock_cfg):
        """Router returning dispatch should be parsed correctly."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"route": "dispatch", "tool_name": "file", "action": "read_file", "params": {"path": "test.py"}}'

        with patch("core.llm.llm.complete", return_value=mock_response):
            result = _call_router("read test.py")
            assert result["route"] == "dispatch"
            assert result["tool_name"] == "file"

    def test_escalate_route(self, mock_cfg):
        """Router returning escalate should be parsed correctly."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"route": "escalate", "reason": "complex task"}'

        with patch("core.llm.llm.complete", return_value=mock_response):
            result = _call_router("do something complex")
            assert result["route"] == "escalate"
            assert "complex task" in result["reason"]

    def test_invalid_json_escalates(self, mock_cfg):
        """Invalid JSON from router should escalate with error."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "not json at all"

        with patch("core.llm.llm.complete", return_value=mock_response):
            result = _call_router("something")
            assert result["route"] == "escalate"
            assert "invalid JSON" in result["reason"]

    def test_llm_error_escalates(self, mock_cfg):
        """LLM error should escalate."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.error = "timeout"

        with patch("core.llm.llm.complete", return_value=mock_response):
            result = _call_router("something")
            assert result["route"] == "escalate"
            assert "timeout" in result["reason"]

    def test_markdown_code_fence_stripped(self, mock_cfg):
        """Markdown code fences should be stripped from router response."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '```json\n{"route": "dispatch", "tool_name": "git", "action": "status", "params": {}}\n```'

        with patch("core.llm.llm.complete", return_value=mock_response):
            result = _call_router("git status")
            assert result["route"] == "dispatch"

    def test_invalid_route_value_escalates(self, mock_cfg):
        """Invalid route value should escalate."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"route": "unknown"}'

        with patch("core.llm.llm.complete", return_value=mock_response):
            result = _call_router("something")
            assert result["route"] == "escalate"
            assert "invalid route" in result["reason"]
