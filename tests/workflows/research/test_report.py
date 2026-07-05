"""tests/workflows/research/test_report.py
Tests for node_report — report generation with citations.
"""
from __future__ import annotations

from unittest.mock import MagicMock


class TestNodeReport:
    def test_node_report_generates_dossier(self, tmp_path, monkeypatch):
        """node_report must call report tool with research preset."""
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)

        mock_report = MagicMock()
        monkeypatch.setattr("tools.report.report", mock_report)

        from workflows.research_impl.nodes.report import node_report

        state = {
            "trace_id": "test-research",
            "goal": "What is Python?",
            "result": "Python is a programming language.",
        }

        # [v1.0] node_report returns {} (LangGraph partial update), not state.
        result = node_report(state)

        assert result == {}  # No state changes — report is a side effect
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["action"] == "report"
        assert call_kwargs["preset"] == "research"
        assert "Python" in call_kwargs["title"]
        assert "sections" in call_kwargs["config"]

    def test_node_report_skips_when_no_result(self, tmp_path, monkeypatch):
        """node_report must skip report generation when result is empty."""
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)

        mock_report = MagicMock()
        monkeypatch.setattr("tools.report.report", mock_report)

        from workflows.research_impl.nodes.report import node_report

        state = {
            "trace_id": "test-research",
            "goal": "What is Python?",
            "result": "",
        }

        # [v1.0] node_report returns {} when result is empty.
        result = node_report(state)

        assert result == {}
        mock_report.assert_not_called()
