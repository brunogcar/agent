"""Agent tool tests — LLM dispatch and error handling."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestAgentLLMDispatch:
    """Test successful LLM dispatch and error paths."""

    def setup_method(self):
        _clear_cache()

    def test_successful_llm_call(self, mock_llm_result):
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="Is this spam?")
            assert result["status"] == "success"
            assert result["role"] == "classify"
            assert "text" in result

    def test_llm_failure_returns_error(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Model timeout"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["status"] == "error"
            assert "error" in result

    def test_temperature_override_passed(self, mock_llm_result):
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="classify", task="test", temperature=0.5)
            call_kwargs = mock_llm.call_args.kwargs
            assert call_kwargs["temperature"] == 0.5

    def test_max_tokens_override_passed(self, mock_llm_result):
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="classify", task="test", max_tokens=100)
            call_kwargs = mock_llm.call_args.kwargs
            assert call_kwargs["max_tokens"] == 100

    def test_no_override_when_negative(self, mock_llm_result):
        """Default temperature=-1 and max_tokens=-1 should NOT be passed."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="classify", task="test")
            call_kwargs = mock_llm.call_args.kwargs
            assert "temperature" not in call_kwargs
            assert "max_tokens" not in call_kwargs

    def test_trace_id_propagated(self, mock_llm_result):
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="classify", task="test", trace_id="abc123")
            call_kwargs = mock_llm.call_args.kwargs
            assert call_kwargs["trace_id"] == "abc123"
