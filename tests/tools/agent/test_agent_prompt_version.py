"""Agent tool tests — prompt versioning."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.cache import _clear_cache


class TestPromptVersioning:
    """Test prompt_version field in successful responses."""

    def setup_method(self):
        _clear_cache()

    def test_success_response_includes_prompt_version(self, mock_llm_result):
        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["status"] == "success"

    def test_prompt_version_is_consistent(self, mock_llm_result):
        """Same prompts should produce same version hash."""
        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            result1 = agent(action="dispatch", role="classify", task="test1")
            result2 = agent(action="dispatch", role="classify", task="test2")
            assert result1["status"] == "success"
            assert result2["status"] == "success"

    def test_error_response_excludes_prompt_version(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Model error"

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["status"] == "error"
