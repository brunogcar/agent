"""tests/workflows/deep_research/test_report.py
Tests for _node_report — report generation + citations.
"""
from __future__ import annotations


class TestNodeReport:
    def test_status_incomplete_when_below_threshold(self, mocker):
        from workflows.deep_research_impl.graph import _node_report
        mocker.patch("core.citations.citations.get_sources", return_value=[])
        state = {
            "knowledge_base": "Partial findings",
            "synthesis": "",
            "completeness": 45.0,
            "completeness_threshold": 85.0,
            "trace_id": "t1",
        }
        result = _node_report(state)
        assert result["status"] == "incomplete"
        assert "Partial findings" in result["report"]

    def test_status_success_when_above_threshold(self, mocker):
        from workflows.deep_research_impl.graph import _node_report
        mocker.patch("core.citations.citations.get_sources", return_value=[])
        state = {
            "knowledge_base": "Complete findings",
            "synthesis": "Complete synthesis",
            "completeness": 90.0,
            "completeness_threshold": 85.0,
            "trace_id": "t1",
        }
        result = _node_report(state)
        assert result["status"] == "success"
        assert "Complete synthesis" in result["report"]


class TestCitationsInReport:
    """v1.1: citations collected by node_search must surface in the report."""

    def test_report_appends_sources_section(self, mocker):
        from workflows.deep_research_impl.graph import _node_report
        mocker.patch(
            "core.citations.citations.get_sources",
            return_value=[
                {"number": 1, "url": "https://a.example", "title": "Source A"},
                {"number": 2, "url": "https://b.example", "title": "Source B"},
            ],
        )
        state = {
            "knowledge_base": "Findings here",
            "synthesis": "Synthesis here",
            "completeness": 90.0,
            "completeness_threshold": 85.0,
            "trace_id": "t1",
        }
        result = _node_report(state)
        assert "## Sources" in result["report"]
        assert "https://a.example" in result["report"]
        assert "https://b.example" in result["report"]
        assert "Source A" in result["report"]

    def test_report_no_sources_no_section(self, mocker):
        """No sources → no Sources section (but report still built)."""
        from workflows.deep_research_impl.graph import _node_report
        mocker.patch("core.citations.citations.get_sources", return_value=[])
        state = {
            "knowledge_base": "Findings",
            "synthesis": "",
            "completeness": 40.0,
            "completeness_threshold": 85.0,
            "trace_id": "t1",
        }
        result = _node_report(state)
        assert "## Sources" not in result["report"]
        assert "Findings" in result["report"]
