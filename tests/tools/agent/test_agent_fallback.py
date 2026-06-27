"""Agent tool tests — retry with fallback role on transient failure."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.cache import _clear_cache


class TestRoleFallback:
    """Test fallback role retry when primary role's LLM call fails."""

    def setup_method(self):
        _clear_cache()

    def test_classify_fallback_to_route(self, mock_llm_result):
        """When classify fails, retry with route role."""
        mock_llm_result.ok = False
        mock_llm_result.error = "Primary model failed"

        fallback_result = type(mock_llm_result)()
        fallback_result.ok = True
        fallback_result.text = "fallback response"
        fallback_result.model = "fallback-model"
        fallback_result.usage = {"total": 10}
        fallback_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, fallback_result]
            result = agent(action="dispatch", role="classify", task="test")

            assert result["status"] == "success"
            assert result["text"] == "fallback response"
            assert mock_llm.call_count == 2

    def test_critique_fallback_to_analyze(self, mock_llm_result):
        """When critique fails, retry with analyze role."""
        mock_llm_result.ok = False
        mock_llm_result.error = "Primary model failed"

        fallback_result = type(mock_llm_result)()
        fallback_result.ok = True
        fallback_result.text = "fallback response"
        fallback_result.model = "fallback-model"
        fallback_result.usage = {"total": 10}
        fallback_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, fallback_result]
            result = agent(action="dispatch", role="critique", task="test")

            assert result["status"] == "success"
            assert mock_llm.call_count == 2

    def test_no_fallback_when_no_fallback_role(self, mock_llm_result):
        """plan role has no fallback — should return error on failure."""
        mock_llm_result.ok = False
        mock_llm_result.error = "Model error"

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="plan", task="test")
            assert result["status"] == "error"

    def test_fallback_failure_returns_error(self, mock_llm_result):
        """If both primary and fallback fail, return error."""
        mock_llm_result.ok = False
        mock_llm_result.error = "Both failed"

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["status"] == "error"
