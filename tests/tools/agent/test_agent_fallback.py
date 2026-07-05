"""Agent tool tests — retry with fallback role on transient failure."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


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

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
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

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, fallback_result]
            result = agent(action="dispatch", role="critique", task="test")

            assert result["status"] == "success"
            assert mock_llm.call_count == 2

    def test_no_fallback_when_no_fallback_role(self, mock_llm_result):
        """plan role has no fallback — should return error on failure."""
        mock_llm_result.ok = False
        mock_llm_result.error = "Model error"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="plan", task="test")
            assert result["status"] == "error"

    def test_fallback_failure_returns_error(self, mock_llm_result):
        """If both primary and fallback fail, return error."""
        mock_llm_result.ok = False
        mock_llm_result.error = "Both failed"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["status"] == "error"

    # ─── Fallback escalation preserved (Bug #10 — design decision) ───────────
    # classify→route and consultor→plan are INTENTIONAL escalation paths.
    # If the primary model is blank/unconfigured or fails transiently, the
    # fallback provides a best-effort answer instead of failing hard.

    def test_classify_fallback_to_route_preserved(self):
        """classify.fallback_role must remain 'route' (intentional escalation)."""
        from tools.agent_ops import ROLES
        fb = ROLES["classify"]["role_config"].get("fallback_role")
        assert fb == "route", (
            f"classify.fallback_role must be 'route' (intentional escalation). Got: {fb!r}"
        )

    def test_consultor_fallback_to_plan_preserved(self):
        """consultor.fallback_role must remain 'plan' (intentional escalation)."""
        from tools.agent_ops import ROLES
        fb = ROLES["consultor"]["role_config"].get("fallback_role")
        assert fb == "plan", (
            f"consultor.fallback_role must be 'plan' (intentional escalation). Got: {fb!r}"
        )

    # ─── Fallback re-trims context (Bug #11) ─────────────────────────────────

    def test_fallback_re_trims_context_for_fallback_budget(self, mock_llm_result):
        """Fallback must re-trim context for the fallback role's budget.

        Previously the fallback reused the primary's trimmed context, which
        could exceed the fallback role's budget when the fallback has a
        smaller context window.
        """
        from tools.agent_ops import ROLES

        # Find a role that has a fallback configured
        roles_with_fallback = [
            (name, cfg["role_config"].get("fallback_role"))
            for name, cfg in ROLES.items()
            if cfg["role_config"].get("fallback_role")
        ]
        if not roles_with_fallback:
            import pytest
            pytest.skip("No roles have fallback_role configured")

        primary_role, fallback_role = roles_with_fallback[0]
        primary_budget = ROLES[primary_role]["role_config"].get("budget_tokens", 0)
        fallback_budget = ROLES[fallback_role]["role_config"].get("budget_tokens", 0)

        if primary_budget == fallback_budget:
            import pytest
            pytest.skip("Primary and fallback have same budget — can't distinguish trims")

        # Primary fails, fallback succeeds
        failed_result = type(mock_llm_result)()
        failed_result.ok = False
        failed_result.error = "timeout"
        failed_result.model = "primary"
        failed_result.usage = {}
        failed_result.text = ""

        success_result = type(mock_llm_result)()
        success_result.ok = True
        success_result.text = "recovered"
        success_result.model = "fallback"
        success_result.usage = {"total": 5}

        large_context = "context " * 2000  # Large enough to need trimming

        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [failed_result, success_result]
            agent(action="dispatch", role=primary_role, task="test", context=large_context)

            assert mock_llm.call_count == 2
            fallback_kwargs = mock_llm.call_args_list[1].kwargs
            fallback_context = fallback_kwargs["context"]

            # The fallback's context should be trimmed to its budget, not the primary's
            assert len(fallback_context) < len(large_context), (
                "Fallback must receive re-trimmed context, not the original. "
                "This regresses the fallback re-trim fix."
            )
