"""Agent tool tests — ROLE_CONFIG validation and budget overrides."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.roles import ROLE_CONFIG, _ROLE_TO_LLM, _API_JSON_ROLES, _JSON_ROLES, _SLEEP_LEARN_ROLES


class TestRoleConfig:
    """Test unified ROLE_CONFIG dict."""

    def test_role_config_covers_all_roles(self):
        """Every role in _ROLE_TO_LLM must have a ROLE_CONFIG entry."""
        for role in _ROLE_TO_LLM:
            assert role in ROLE_CONFIG, f"Missing ROLE_CONFIG for {role}"

    def test_role_config_has_required_fields(self):
        """Each role config must have llm_role, json_mode, budget_chars, cacheable."""
        required = {"llm_role", "json_mode", "budget_chars", "cacheable"}
        for role, cfg in ROLE_CONFIG.items():
            missing = required - set(cfg.keys())
            assert not missing, f"Role '{role}' missing fields: {missing}"

    def test_backward_compat_aliases_match(self):
        """_ROLE_TO_LLM and _JSON_ROLES must match ROLE_CONFIG."""
        assert _ROLE_TO_LLM == {k: v["llm_role"] for k, v in ROLE_CONFIG.items()}
        api_roles = {k for k, v in ROLE_CONFIG.items() if v["json_mode"] == "api"}
        assert _API_JSON_ROLES == api_roles

    def test_cacheable_roles_are_deterministic(self):
        """Only classify and route should be cacheable (deterministic outputs)."""
        cacheable = {k for k, v in ROLE_CONFIG.items() if v["cacheable"]}
        assert cacheable == {"classify", "route"}

    def test_sleep_learn_roles_exclude_router(self):
        """Router roles (15s) must not be in sleep-learn set."""
        assert "classify" not in _SLEEP_LEARN_ROLES
        assert "route" not in _SLEEP_LEARN_ROLES
        assert "research" in _SLEEP_LEARN_ROLES


class TestBudgetOverrides:
    """Test per-role context budget overrides."""

    def test_router_uses_small_budget(self, mock_llm_result):
        """classify role should use 16K char budget (4K tokens)."""
        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.return_value = mock_llm_result
            agent(role="classify", task="test", context="x" * 20000)

            call_kwargs = mock_llm.call_args.kwargs
            # context should be trimmed to ~16K, not 32K
            assert len(call_kwargs["context"]) < 20000

    def test_planner_uses_large_budget(self, mock_llm_result):
        """plan role should use 128K char budget (32K tokens)."""
        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.return_value = mock_llm_result
            agent(role="plan", task="test", context="x" * 50000)

            call_kwargs = mock_llm.call_args.kwargs
            # 50K chars should NOT be trimmed (fits in 128K budget)
            assert len(call_kwargs["context"]) == 50000
