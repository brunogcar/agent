"""Tests for DISPATCH registry, metadata coverage, and PRESETS."""
from tools.report_core._registry import DISPATCH, DISPATCH_METADATA, PRESETS


class TestRegistry:
    """Auto-discovered dispatch table and metadata."""

    def test_dispatch_keys(self):
        expected = {"chart", "map", "report", "dashboard", "diagram", "export",
                    "compare", "timeline", "scorecard", "list", "help"}
        assert set(DISPATCH.get("report", {}).keys()) == expected

    def test_metadata_covers_all_actions(self):
        dispatch_keys = set(DISPATCH.get("report", {}).keys())
        metadata_keys = set(DISPATCH_METADATA.keys())
        assert metadata_keys == dispatch_keys

    def test_presets_exist(self):
        expected = {"financial", "code_audit", "research", "system_health",
                    "compare", "timeline", "scorecard"}
        assert set(PRESETS.keys()) == expected

    def test_all_actions_have_func(self):
        for name, info in DISPATCH.get("report", {}).items():
            assert "func" in info, f"Action {name} missing func"
            assert callable(info["func"]), f"Action {name} func not callable"

    def test_all_actions_have_help_text(self):
        for name, info in DISPATCH.get("report", {}).items():
            assert "help" in info, f"Action {name} missing help"
            assert isinstance(info["help"], str), f"Action {name} help not a string"

    def test_list_action_returns_catalog(self):
        from tools.report_core.actions.list import run_list
        result = run_list()
        assert result["type"] == "list"
        assert result["count"] == 11
        assert len(result["actions"]) == 11

    def test_help_action_specific(self):
        from tools.report_core.actions.help import run_help
        result = run_help(data="chart")
        assert result["type"] == "help"
        assert result["action"] == "chart"
        assert "description" in result

    def test_help_action_all(self):
        from tools.report_core.actions.help import run_help
        result = run_help()
        assert result["type"] == "help"
        assert result["count"] == 11
        assert "actions" in result

    def test_help_unknown_action(self):
        from tools.report_core.actions.help import run_help
        result = run_help(data="nonexistent")
        assert "error" in result
        assert "known_actions" in result
