"""Agent tool tests — DISPATCH registry register/unregister."""
from __future__ import annotations

from tools.agent_ops._registry import DISPATCH, register_action, unregister_action


class TestUnregisterAction:
    """unregister_action removes handlers from DISPATCH (Bug #27).

    Useful for hot-reload (unregister old handler, re-import module to
    register updated one), testing (remove mock actions after a suite),
    and feature flags (disable an action at runtime).
    """

    def test_unregister_existing_action(self):
        """Register then unregister an action — must return True and remove it."""
        @register_action("test_tool", "test_action_unreg")
        def handler():
            return {"status": "success"}

        assert "test_action_unreg" in DISPATCH.get("test_tool", {})
        result = unregister_action("test_tool", "test_action_unreg")
        assert result is True
        assert "test_action_unreg" not in DISPATCH.get("test_tool", {})

    def test_unregister_nonexistent_returns_false(self):
        """Unregistering a missing action must return False, not raise."""
        result = unregister_action("nonexistent_tool", "nonexistent_action")
        assert result is False

    def test_unregister_cleans_empty_namespace(self):
        """When the last action in a tool namespace is removed, the namespace
        key must be cleaned up from DISPATCH to keep the table tidy."""
        @register_action("cleanup_test", "action1")
        def handler():
            return {"status": "success"}

        unregister_action("cleanup_test", "action1")
        assert "cleanup_test" not in DISPATCH, (
            "Empty tool namespace must be cleaned up after last action removed."
        )
