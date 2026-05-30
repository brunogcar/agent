"""
tests/tools/agent/test_agent_tool.py
Deep tests for the agent meta-tool dispatch, JSON parsing, and role mapping.
"""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from tools.agent_tool import agent, _SYSTEM_PROMPTS, _ROLE_TO_LLM

class TestAgentToolValidation:
    def test_unknown_role_returns_error(self):
        result = agent(role="unknown_role", task="do something")
        assert result["status"] == "error"
        assert "Unknown role" in result["error"]

    def test_missing_task_returns_error(self):
        result = agent(role="classify", task="")
        assert result["status"] == "error"
        assert "task is required" in result["error"]

    def test_all_roles_have_system_prompts(self):
        """Every role in _ROLE_TO_LLM + vision must have a system prompt."""
        all_roles = set(_ROLE_TO_LLM.keys()) | {"vision"}
        for role in all_roles:
            assert role in _SYSTEM_PROMPTS, f"Missing system prompt for role: {role}"

class TestAgentToolVisionDelegation:
    def test_vision_delegates_to_vision_tool(self):
        """Vision role must NOT call llm.complete, it must call tools.vision.vision."""
        mock_vision_res = {"status": "success", "text": "I see a cat"}
        
        # Patch where it is imported inside the function
        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            result = agent(role="vision", task="What is this?", context="img.png")
            
        assert mock_vis.called
        assert result["status"] == "success"
        assert result["text"] == "I see a cat"

class TestAgentToolLLMDispatch:
    def test_successful_llm_call_returns_success(self):
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "Positive"
        mock_result.model = "nemotron"
        mock_result.elapsed = 1.0
        mock_result.usage = {"prompt_tokens": 10, "completion_tokens": 5}
        mock_result.parsed = None
        
        with patch("tools.agent_tool.llm.complete", return_value=mock_result):
            result = agent(role="classify", task="Is this good?")
            
        assert result["status"] == "success"
        assert result["text"] == "Positive"
        assert result["role"] == "classify"

    def test_llm_failure_returns_error(self):
        mock_result = MagicMock()
        mock_result.ok = False
        mock_result.error = "Timeout"
        mock_result.elapsed = 60.0
        mock_result.model = "nemotron"
        
        with patch("tools.agent_tool.llm.complete", return_value=mock_result):
            result = agent(role="classify", task="Is this good?")
            
        assert result["status"] == "error"
        assert result["error"] == "Timeout"

class TestAgentToolJSONParsing:
    def test_json_role_parses_valid_json(self):
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = '{"workflow": "research", "tool": "web", "complexity": 5, "reason": "test"}'
        mock_result.model = "nemotron"
        mock_result.elapsed = 1.0
        mock_result.usage = {}
        mock_result.parsed = None  # Simulate prompt-only JSON parsing
        
        with patch("tools.agent_tool.llm.complete", return_value=mock_result):
            result = agent(role="route", task="Search the web")
            
        assert result["status"] == "success"
        assert "parsed" in result
        assert result["parsed"]["workflow"] == "research"

    def test_json_role_handles_invalid_json_gracefully(self):
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "I cannot output JSON, here is my thought process..."
        mock_result.model = "qwen"
        mock_result.elapsed = 1.0
        mock_result.usage = {}
        mock_result.parsed = None
        
        with patch("tools.agent_tool.llm.complete", return_value=mock_result):
            result = agent(role="plan", task="Plan this")
            
        assert result["status"] == "success"
        assert result["parsed"] == {}
        assert "parse_warning" in result

    def test_json_role_strips_markdown_fences(self):
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = '```json\n{"verdict": "APPROVE"}\n```'
        mock_result.model = "hermes"
        mock_result.elapsed = 1.0
        mock_result.usage = {}
        mock_result.parsed = None
        
        with patch("tools.agent_tool.llm.complete", return_value=mock_result):
            result = agent(role="review", task="Review this")
            
        assert result["parsed"]["verdict"] == "APPROVE"