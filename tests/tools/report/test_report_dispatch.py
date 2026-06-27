"""Tests for report tool dispatch and unknown actions."""
from tools.report import report


class TestDispatch:
    """Dispatcher routes actions and handles unknown/empty actions."""

    def test_unknown_action(self):
        """Unknown action should list valid atomic action names."""
        result = report(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        # Should include new atomic names
        assert "chart" in result["error"] or "dashboard" in result["error"]

    def test_empty_action(self):
        """Empty action should return clear error about required param."""
        result = report(action="")
        assert result["status"] == "error"
        assert "action parameter is required" in result["error"]

    def test_whitespace_action(self):
        """Whitespace-only action should be treated as empty."""
        result = report(action="   ")
        assert result["status"] == "error"
        assert "action parameter is required" in result["error"]

    def test_case_insensitive_action(self):
        """Action names should be case-insensitive."""
        result = report(action="CHART", title="T", data={"x": [1], "y": [2]})
        # Should succeed (or at least not fail on unknown action)
        assert result["status"] == "success" or "Unknown action" not in result.get("error", "")
