"""Tests for report.list action via facade."""
from tools.report import report


class TestListAction:
    """List all available report actions via facade."""

    def test_list_via_facade(self):
        result = report(action="list", trace_id="test-list")
        assert result["status"] == "success"
        assert result["type"] == "list"
        assert result["count"] == 11
        actions = result["actions"]
        names = [a["name"] for a in actions]
        assert "chart" in names
        assert "dashboard" in names
        assert "help" in names
        assert "list" in names

    def test_list_includes_descriptions(self):
        result = report(action="list", trace_id="test-list-desc")
        actions = result["actions"]
        for a in actions:
            assert "description" in a
            assert "required_params" in a
            assert "config_keys" in a

    def test_list_sorted(self):
        result = report(action="list", trace_id="test-list-sort")
        names = [a["name"] for a in result["actions"]]
        assert names == sorted(names)
