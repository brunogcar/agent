"""Tests for report.help action via facade."""
from tools.report import report


class TestHelpAction:
    """Get detailed help for specific report actions via facade."""

    def test_help_specific_action(self):
        result = report(action="help", data="chart", trace_id="test-help-chart")
        assert result["status"] == "success"
        assert result["type"] == "help"
        assert result["action"] == "chart"
        assert "description" in result
        assert "required_params" in result
        assert "config_keys" in result

    def test_help_all_actions(self):
        result = report(action="help", trace_id="test-help-all")
        assert result["status"] == "success"
        assert result["type"] == "help"
        assert result["count"] == 11
        assert "actions" in result
        assert "chart" in result["actions"]

    def test_help_unknown_action(self):
        result = report(action="help", data="nonexistent", trace_id="test-help-bad")
        # help action returns error info inside the result dict, not report_fail
        assert "error" in result
        assert "known_actions" in result
        assert "nonexistent" in result["error"] or "Unknown action" in result.get("error", "")

    def test_help_case_insensitive(self):
        result = report(action="help", data="CHART", trace_id="test-help-case")
        assert result["status"] == "success"
        assert result["action"] == "chart"
