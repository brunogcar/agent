"""Agent tool tests — sleep-learn integration."""
from __future__ import annotations

from unittest.mock import patch

# v1.4 fix: ensure core.sleep_learn.injector is imported before patch() tries
# to resolve it as an attribute of core. Without this, patch("core.sleep_learn.
# injector.inject_rules_into_prompt") fails with AttributeError because
# core.sleep_learn hasn't been loaded yet (dispatch.py imports it lazily).
import core.sleep_learn.injector  # noqa: F401

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestAgentSleepLearnIntegration:
    """Test inject_rules_into_prompt wiring in agent() dispatch path."""

    def setup_method(self):
        _clear_cache()

    def test_inject_rules_called_for_high_latency_role(self, mock_llm_result):
        """sleep-learn injection fires for roles with large budgets."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm, \
             patch("core.sleep_learn.injector.inject_rules_into_prompt") as mock_inject:
            mock_inject.return_value = "injected prompt"
            agent(action="dispatch", role="research", task="test")

            assert mock_inject.called

    def test_inject_rules_not_called_for_router_roles(self, mock_llm_result):
        """Router roles (small budget) skip sleep-learn to avoid overhead."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm, \
             patch("core.sleep_learn.injector.inject_rules_into_prompt") as mock_inject:
            agent(action="dispatch", role="classify", task="test")

            assert not mock_inject.called

    def test_inject_rules_failure_falls_back_to_original_prompt(self, mock_llm_result):
        """If inject_rules_into_prompt raises, agent still succeeds with original prompt."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm, \
             patch("core.sleep_learn.injector.inject_rules_into_prompt") as mock_inject:
            mock_inject.side_effect = Exception("Injection failed")
            result = agent(action="dispatch", role="research", task="test")

            assert result["status"] == "success"

    def test_inject_rules_respects_trace_id(self, mock_llm_result):
        """trace_id propagates to inject_rules_into_prompt."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm, \
             patch("core.sleep_learn.injector.inject_rules_into_prompt") as mock_inject:
            mock_inject.return_value = "injected prompt"
            agent(action="dispatch", role="research", task="test", trace_id="abc123")

            call_kwargs = mock_inject.call_args.kwargs
            assert call_kwargs["trace_id"] == "abc123"

    def test_inject_rules_skipped_when_module_unavailable(self, mock_llm_result):
        """If core.sleep_learn is not installed, agent works without it."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="research", task="test")
            assert result["status"] == "success"
