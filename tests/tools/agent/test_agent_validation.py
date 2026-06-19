"""Agent tool tests — validation and role coverage."""
from __future__ import annotations

from tools.agent import agent
from tools.agent_core.prompts import _SYSTEM_PROMPTS
from tools.agent_core.roles import _ROLE_TO_LLM


class TestAgentValidation:
    """Test input validation and role coverage."""

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

    def test_role_case_insensitive(self, mock_llm_result):
        """Role parameter should be case-insensitive."""
        from unittest.mock import patch
        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="CLASSIFY", task="test")
            assert result["status"] == "success"
            assert result["role"] == "classify"
