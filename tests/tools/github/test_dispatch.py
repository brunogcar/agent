"""Tests for github tool dispatch and unknown actions.

Mirrors tests/tools/swarm/test_dispatch.py — same pattern: facade-level
dispatch behavior + DISPATCH registry sanity check.
"""
from __future__ import annotations

from tools.github import github


class TestDispatch:
    """Dispatcher routes actions and handles unknown actions."""

    def test_unknown_action(self):
        """Unknown action should list valid atomic action names."""
        result = github(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        # All 7 valid actions should be listed in the error message
        assert "pr_create" in result["error"]
        assert "pr_list" in result["error"]
        assert "pr_get" in result["error"]
        assert "pr_review" in result["error"]
        assert "pr_merge" in result["error"]
        assert "pr_comment" in result["error"]
        assert "push" in result["error"]

    def test_empty_action(self):
        """Empty action should return a clear 'action is required' error."""
        result = github(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"]

    def test_dispatch_has_7_actions(self):
        """DISPATCH['github'] must contain exactly the 7 registered actions."""
        from tools.github_ops._registry import DISPATCH
        actions = DISPATCH.get("github", {})
        assert len(actions) == 7
        expected = {
            "pr_create", "pr_list", "pr_get",
            "pr_review", "pr_merge", "pr_comment",
            "push",
        }
        assert set(actions.keys()) == expected

    def test_duration_ms_present_on_handler_result(self, mock_httpx_client):
        """duration_ms should be injected on every successful handler result.

        Uses pr_list (lightweight, no required params beyond is_configured())
        with a mocked httpx client so no real API call is made.
        """
        # Mock returns an empty list of PRs
        mock_resp = mock_httpx_client.get.return_value
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.text = ""

        result = github(action="pr_list")

        assert result["status"] == "success"
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))
        assert result["duration_ms"] >= 0


class TestRegistry:
    """Verify all 7 actions are registered with proper metadata."""

    def test_all_actions_have_metadata(self):
        from tools.github_ops._registry import DISPATCH
        for name, info in DISPATCH["github"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert "examples" in info, f"{name} missing examples"
            assert callable(info["func"]), f"{name} func not callable"
            assert info["help"], f"{name} has empty help_text"
            assert info["examples"], f"{name} has empty examples list"
