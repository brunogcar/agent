"""Tests for git tool dispatch and unknown actions."""
from tools.git import git


class TestDispatch:
    """Dispatcher routes actions and handles unknown actions."""

    def test_unknown_action(self):
        """Unknown action should list valid atomic action names."""
        result = git(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        # Should include new atomic names
        assert "branch_list" in result["error"] or "branch_create" in result["error"]

    def test_empty_action(self):
        """Empty action should return unknown action error."""
        result = git(action="")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
