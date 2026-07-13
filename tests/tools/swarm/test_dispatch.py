"""Tests for swarm tool dispatch and unknown actions.

v1.0.1:
  - test_action_case_insensitive now uses mock_llm_empty_registry (was using
    the real llm registry, risking real billed API calls if the test env
    had cloud providers configured).
  - Added input-validation tests for max_tokens / timeout (P3-2).
"""
from __future__ import annotations
from tools.swarm import swarm


class TestDispatch:
    """Dispatcher routes actions and handles unknown actions."""

    def test_unknown_action(self):
        """Unknown action should list valid actions."""
        result = swarm(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        assert "consensus" in result["error"]
        assert "race" in result["error"]

    def test_empty_action(self):
        """Empty action should return clear error."""
        result = swarm(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"]

    def test_action_case_insensitive(self, mock_llm_empty_registry):
        """Action should be case-insensitive.

        v1.0.1: Now uses mock_llm_empty_registry. Previously used the real
        llm registry — if the test env had OPENAI_API_KEY+OPENAI_BASE_MODEL
        set, this would have made a real billed API call (INSTRUCTIONS.md #37
        violation). Now asserts the specific 'No cloud providers' error to
        prove the action was dispatched (not rejected as unknown).
        """
        result = swarm(action="CONSENSUS", question="test")
        assert result["status"] == "error"
        assert "Unknown action" not in result.get("error", "")
        assert "No cloud providers" in result["error"]

    def test_duration_ms_on_handler_result(self, mock_llm_registry):
        """duration_ms should be present when a handler actually runs."""
        result = swarm(action="list_providers")
        assert result["status"] == "success"
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))


class TestInputValidation:
    """v1.0.1: Numeric bounds for max_tokens and timeout (P3-2)."""

    def test_max_tokens_too_low(self, mock_llm_registry):
        result = swarm(action="list_providers", max_tokens=0)
        assert result["status"] == "error"
        assert "max_tokens" in result["error"]
        assert result.get("error_code") == "INVALID_ACTION"

    def test_max_tokens_negative(self, mock_llm_registry):
        result = swarm(action="list_providers", max_tokens=-1)
        assert result["status"] == "error"
        assert "max_tokens" in result["error"]

    def test_max_tokens_too_high(self, mock_llm_registry):
        result = swarm(action="list_providers", max_tokens=99999)
        assert result["status"] == "error"
        assert "max_tokens" in result["error"]

    def test_max_tokens_at_bounds(self, mock_llm_registry):
        """1 and 8192 are valid bounds — should pass validation."""
        for mt in (1, 8192):
            result = swarm(action="list_providers", max_tokens=mt)
            assert result["status"] == "success", f"max_tokens={mt} should be valid"

    def test_timeout_too_low(self, mock_llm_registry):
        result = swarm(action="list_providers", timeout=0)
        assert result["status"] == "error"
        assert "timeout" in result["error"]

    def test_timeout_negative(self, mock_llm_registry):
        result = swarm(action="list_providers", timeout=-1)
        assert result["status"] == "error"
        assert "timeout" in result["error"]

    def test_timeout_too_high(self, mock_llm_registry):
        result = swarm(action="list_providers", timeout=301)
        assert result["status"] == "error"
        assert "timeout" in result["error"]

    def test_timeout_at_bounds(self, mock_llm_registry):
        """1 and 300 are valid bounds — should pass validation."""
        for t in (1, 300):
            result = swarm(action="list_providers", timeout=t)
            assert result["status"] == "success", f"timeout={t} should be valid"

    def test_validation_runs_before_action_check(self):
        """Invalid max_tokens should fail even for an unknown action."""
        result = swarm(action="nonexistent", max_tokens=-1)
        # Validation happens after action-required check but before dispatch lookup.
        # With a non-empty action, validation fires first.
        assert result["status"] == "error"
        assert "max_tokens" in result["error"]


class TestRegistry:
    """Verify all 5 actions are registered in DISPATCH."""

    def test_dispatch_has_5_actions(self):
        from tools.swarm_ops._registry import DISPATCH
        actions = DISPATCH.get("swarm", {})
        assert len(actions) == 5
        expected = {"consensus", "race", "vote", "compare", "list_providers"}
        assert set(actions.keys()) == expected

    def test_all_actions_have_metadata(self):
        from tools.swarm_ops._registry import DISPATCH
        for name, info in DISPATCH["swarm"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert callable(info["func"]), f"{name} func not callable"
