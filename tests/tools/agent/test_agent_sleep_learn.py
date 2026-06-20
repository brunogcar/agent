"""Agent tool tests — sleep-learn integration."""
from __future__ import annotations

from unittest.mock import patch, ANY

from tools.agent import agent
from tools.agent_core.cache import _clear_cache


class TestAgentSleepLearnIntegration:
    """Test inject_rules_into_prompt wiring in agent() dispatch path."""

    def setup_method(self):
        """Clear response cache between tests for cacheable roles."""
        _clear_cache()

    def test_inject_rules_called_for_high_latency_role(self, mock_llm_result):
        """sleep-learn injection fires for roles with 60s+ budgets."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm,              patch("tools.agent._inject_rules", return_value="INJECTED PROMPT") as mock_inject:
            result = agent(role="research", task="Find Python docs")

        assert result["status"] == "success"
        mock_inject.assert_called_once_with(
            goal="Find Python docs",
            system_prompt=ANY,
            trace_id="",
        )
        # Verify injected prompt reaches llm.complete()
        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["system"] == "INJECTED PROMPT"

    def test_inject_rules_not_called_for_router_roles(self, mock_llm_result):
        """Router roles (15s budget) skip sleep-learn to avoid overhead."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm,              patch("tools.agent._inject_rules", return_value="INJECTED") as mock_inject:
            result = agent(role="classify", task="Is this a bug?")

        assert result["status"] == "success"
        mock_inject.assert_not_called()
        # Original system prompt used, not injected
        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["system"] != "INJECTED"

    def test_inject_rules_failure_falls_back_to_original_prompt(self, mock_llm_result):
        """If inject_rules_into_prompt raises, agent still succeeds with original prompt."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm,              patch("tools.agent._inject_rules", side_effect=RuntimeError("ChromaDB down")) as mock_inject:
            result = agent(role="plan", task="Plan a refactor")

        assert result["status"] == "success"
        mock_inject.assert_called_once()
        # llm.complete() called with original prompt, not crashed
        call_kwargs = mock_llm.call_args.kwargs
        assert "system" in call_kwargs
        assert call_kwargs["system"] != "INJECTED"

    def test_inject_rules_respects_trace_id(self, mock_llm_result):
        """trace_id propagates to inject_rules_into_prompt."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result),              patch("tools.agent._inject_rules", return_value="PROMPT") as mock_inject:
            agent(role="code", task="Fix bug", trace_id="trace-42")

        mock_inject.assert_called_once()
        assert mock_inject.call_args.kwargs["trace_id"] == "trace-42"

    def test_inject_rules_skipped_when_module_unavailable(self, mock_llm_result):
        """If core.sleep_learn is not installed, agent works without it."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm,              patch("tools.agent._inject_rules", None):
            result = agent(role="review", task="Review patch")

        assert result["status"] == "success"
        call_kwargs = mock_llm.call_args.kwargs
        assert "system" in call_kwargs
