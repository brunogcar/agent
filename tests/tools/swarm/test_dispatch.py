"""Tests for swarm tool dispatch and unknown actions."""
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

    def test_action_case_insensitive(self):
        """Action should be case-insensitive."""
        result = swarm(action="CONSENSUS", question="test")
        # Will fail because no providers, but should NOT fail with "unknown action"
        assert "Unknown action" not in result.get("error", "")

    def test_duration_ms_on_handler_result(self, mock_llm_registry):
        """duration_ms should be present when a handler actually runs."""
        result = swarm(action="list_providers")
        assert result["status"] == "success"
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))


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
