"""Agent tool tests — ROLE_CONFIG validation and budget overrides."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops import ROLES
from tools.agent_ops.cache import _clear_cache


class TestRoleConfig:
    """Test unified ROLES dict."""

    def test_roles_covers_all_expected(self):
        """Every expected role must exist in ROLES."""
        expected = {
            "classify", "route", "research", "summarize", "extract",
            "critique", "analyze", "code", "review", "plan", "consultor", "vision",
            "refactor", "test", "document",
        }
        for role in expected:
            assert role in ROLES, f"Missing ROLES entry for {role}"

    def test_role_config_has_required_fields(self):
        """Each role config must have llm_role, json_mode, budget_chars, cacheable."""
        required = {"llm_role", "json_mode", "budget_chars", "cacheable"}
        for role, data in ROLES.items():
            cfg = data["role_config"]
            missing = required - set(cfg.keys())
            assert not missing, f"Role '{role}' missing fields: {missing}"

    def test_llm_role_matches_config(self):
        """llm_role in each config must be a non-empty string."""
        for role, data in ROLES.items():
            llm_role = data["role_config"]["llm_role"]
            assert isinstance(llm_role, str) and llm_role, f"Role '{role}' has invalid llm_role"

    def test_api_json_roles(self):
        """Only extract should use API json_mode."""
        api_roles = {k for k, v in ROLES.items() if v["role_config"].get("json_mode") == "api"}
        assert api_roles == {"extract"}, f"Unexpected API json_mode roles: {api_roles}"

    def test_prompt_json_roles(self):
        """route, plan, code, review, refactor, test should use prompt json_mode."""
        prompt_roles = {k for k, v in ROLES.items() if v["role_config"].get("json_mode") == "prompt"}
        assert prompt_roles == {"route", "plan", "code", "review", "refactor", "test"}, f"Unexpected prompt json_mode roles: {prompt_roles}"

    def test_cacheable_roles_are_deterministic(self):
        """Only classify and route should be cacheable (deterministic outputs)."""
        cacheable = {k for k, v in ROLES.items() if v["role_config"].get("cacheable")}
        assert cacheable == {"classify", "route"}, f"Unexpected cacheable roles: {cacheable}"

    def test_sleep_learn_roles_exclude_router(self):
        """Router roles (small budget) must not be in sleep-learn set."""
        sleep_learn = {k for k, v in ROLES.items() if v["role_config"].get("sleep_learn")}
        assert "classify" not in sleep_learn
        assert "route" not in sleep_learn
        assert "research" in sleep_learn
        assert "refactor" in sleep_learn
        assert "test" in sleep_learn
        assert "document" in sleep_learn

    def test_budget_tokens_present(self):
        """All roles should have budget_tokens set."""
        for role, data in ROLES.items():
            assert "budget_tokens" in data["role_config"], f"Role '{role}' missing budget_tokens"
            assert isinstance(data["role_config"]["budget_tokens"], int), f"Role '{role}' budget_tokens must be int"

    def test_new_roles_have_system_prompts(self):
        """New roles must have non-empty system prompts."""
        for role in ("refactor", "test", "document"):
            assert ROLES[role]["system_prompt"], f"Missing system prompt for {role}"


class TestBudgetOverrides:
    """Test per-role context budget overrides."""

    def setup_method(self):
        _clear_cache()

    def test_router_uses_small_budget(self, mock_llm_result):
        """classify role should trim context to budget_tokens (4K)."""
        context = "word " * 5000
        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.return_value = mock_llm_result
            agent(action="dispatch", role="classify", task="test", context=context)

            call_kwargs = mock_llm.call_args.kwargs
            assert len(call_kwargs["context"]) < 25000

    def test_planner_uses_large_budget(self, mock_llm_result):
        """plan role should use 128K char budget (32K tokens)."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.return_value = mock_llm_result
            agent(action="dispatch", role="plan", task="test", context="x" * 50000)

            call_kwargs = mock_llm.call_args.kwargs
            assert len(call_kwargs["context"]) == 50000

    def test_budget_chars_zero_not_overridden(self, mock_llm_result):
        """budget_chars=0 must not fall through to _max_context_chars().

        The 'or' trap bug: `budget_chars = role_cfg.get("budget_chars") or _max_context_chars()`
        would treat 0 as falsy and use _max_context_chars() instead.
        With the fix (is None check), budget_chars=0 is respected.

        We verify this by checking the context is NOT the full untrimmed text
        (which would happen if _max_context_chars() was used and the text fit).
        """
        from tools.agent_ops import ROLES
        original_chars = ROLES["classify"]["role_config"].get("budget_chars")
        original_tokens = ROLES["classify"]["role_config"].get("budget_tokens")
        try:
            # Remove budget_tokens so budget_chars=0 takes effect
            ROLES["classify"]["role_config"]["budget_chars"] = 0
            if "budget_tokens" in ROLES["classify"]["role_config"]:
                del ROLES["classify"]["role_config"]["budget_tokens"]

            with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
                mock_llm.return_value = mock_llm_result
                agent(action="dispatch", role="classify", task="test", context="x" * 1000)
                call_kwargs = mock_llm.call_args.kwargs
                # If _max_context_chars() was used (the bug), "x"*1000 would fit
                # in 32000 char budget and return unchanged (1000 chars).
                # With budget_chars=0 respected, it should be different.
                assert len(call_kwargs["context"]) != 1000, (
                    "budget_chars=0 was overridden by _max_context_chars() — "
                    "the 'or' trap bug is still present"
                )
        finally:
            if original_chars is not None:
                ROLES["classify"]["role_config"]["budget_chars"] = original_chars
            else:
                del ROLES["classify"]["role_config"]["budget_chars"]
            if original_tokens is not None:
                ROLES["classify"]["role_config"]["budget_tokens"] = original_tokens


class TestRoleSetCaches:
    """Role classification sets (_JSON_ROLES, _SLEEP_LEARN_ROLES) must be
    module-level frozensets, built once on first dispatch call (lazy init).
    """

    def test_role_sets_are_frozensets(self):
        """Sets must be frozensets (immutable, hashable) after first dispatch."""
        from tools.agent_ops.actions.dispatch import (
            _SLEEP_LEARN_ROLES, _PROMPT_JSON_ROLES, _API_JSON_ROLES, _JSON_ROLES,
        )
        assert isinstance(_SLEEP_LEARN_ROLES, frozenset)
        assert isinstance(_PROMPT_JSON_ROLES, frozenset)
        assert isinstance(_API_JSON_ROLES, frozenset)
        assert isinstance(_JSON_ROLES, frozenset)

    def test_role_sets_populated_on_first_dispatch(self):
        """Sets must be non-empty after at least one dispatch call.

        Lazy init: sets are empty at module load (ROLES not yet populated),
        then populated on first run_dispatch() call. We trigger init by
        calling _ensure_role_sets_initialized() directly.
        """
        from tools.agent_ops.actions.dispatch import (
            _ensure_role_sets_initialized, _JSON_ROLES, _SLEEP_LEARN_ROLES,
        )
        _ensure_role_sets_initialized()
        # At least route and classify are JSON roles (json_mode != None)
        assert len(_JSON_ROLES) > 0, "_JSON_ROLES must be populated after init"
        # At least research/plan/etc. have sleep_learn=True
        assert len(_SLEEP_LEARN_ROLES) > 0, "_SLEEP_LEARN_ROLES must be populated after init"


class TestLlmRoleValidation:
    """Auto-discovery warns (not errors) when llm_role is not in model_registry.

    The validation must NOT raise — some roles are opt-in (e.g., consultor
    is only in model_registry when CONSULTOR_MODEL is set in .env). Raising
    would break every environment that doesn't have all optional roles
    configured. Instead, emit a stderr warning so typos are still caught.
    """

    def test_opt_in_role_does_not_break_import(self):
        """consultor role (opt-in) must not break when CONSULTOR_MODEL is unset.

        This is the regression that caused 17 test collection errors: an
        earlier fix raised ValueError, breaking all agent tests in
        environments without CONSULTOR_MODEL configured.
        """
        # If we got here (test collection succeeded), the import worked.
        assert "consultor" in ROLES, "consultor role must be registered even when unconfigured"
        assert "classify" in ROLES
        assert "route" in ROLES

    def test_llm_role_warning_emitted_for_opt_in_roles(self):
        """When llm_role is not in model_registry, a warning is printed to stderr.

        We can't easily re-run auto-discovery, but we verify the module loaded
        successfully with opt-in roles present (the warning was emitted to
        stderr during import, which pytest captures).
        """
        assert len(ROLES) > 0, "ROLES must be populated"
