"""Agent tool tests — prompt versioning."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestPromptVersioning:
    """Test prompt_version field in successful responses."""

    def setup_method(self):
        from tools.agent import _CACHE
        _CACHE.clear()

    def test_success_response_includes_prompt_version(self, mock_llm_result):
        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="classify", task="test")

        assert "prompt_version" in result
        assert isinstance(result["prompt_version"], str)
        assert len(result["prompt_version"]) == 8  # hex digest[:8]

    def test_prompt_version_is_consistent(self, mock_llm_result):
        """Same prompts should produce same version hash."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result1 = agent(role="classify", task="test1")
            result2 = agent(role="route", task="test2")

        assert result1["prompt_version"] == result2["prompt_version"]

    def test_error_response_excludes_prompt_version(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Timeout"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="classify", task="test")

        assert result["status"] == "error"
        assert "prompt_version" not in result
