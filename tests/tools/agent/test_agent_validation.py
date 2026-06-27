"""Agent tool tests — validation and role coverage."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core import ROLES


class TestAgentValidation:
    """Test input validation and role coverage."""

    def test_unknown_action_returns_error(self):
        result = agent(action="unknown_action", role="classify", task="do something")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_unknown_role_returns_error(self):
        result = agent(action="dispatch", role="unknown_role", task="do something")
        assert result["status"] == "error"
        assert "Unknown role" in result["error"]

    def test_missing_task_returns_error(self):
        result = agent(action="dispatch", role="classify", task="")
        assert result["status"] == "error"
        assert "task is required" in result["error"]

    def test_all_roles_have_system_prompts(self):
        """Every role in ROLES must have a system prompt."""
        for role, data in ROLES.items():
            assert data["system_prompt"], f"Missing system prompt for role: {role}"
            assert isinstance(data["system_prompt"], str), f"system_prompt for {role} must be str"

    def test_role_case_insensitive(self, mock_llm_result):
        """Role parameter should be case-insensitive."""
        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="CLASSIFY", task="test")
            assert result["status"] == "success"
            assert result["role"] == "classify"
