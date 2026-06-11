"""
tests/workflows/test_workflow_reports.py -- Phase 4: workflow auto-report nodes.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestResearchReport:
    def test_node_report_generates_dossier(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        mock_report = MagicMock()
        monkeypatch.setattr("tools.report.report", mock_report)

        from workflows.research import node_report

        state = {
            "trace_id": "test-research",
            "goal": "What is Python?",
            "result": "Python is a programming language.",
        }

        result = node_report(state)

        assert result["trace_id"] == "test-research"
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["action"] == "report"
        assert call_kwargs["preset"] == "research"
        assert "Python" in call_kwargs["title"]
        assert "sections" in call_kwargs["config"]

    def test_node_report_skips_when_no_result(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        mock_report = MagicMock()
        monkeypatch.setattr("tools.report.report", mock_report)

        from workflows.research import node_report

        state = {
            "trace_id": "test-research",
            "goal": "What is Python?",
            "result": "",
        }

        result = node_report(state)

        assert result["trace_id"] == "test-research"
        mock_report.assert_not_called()


class TestAutocodeReport:
    def test_node_report_generates_audit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        mock_report = MagicMock()
        monkeypatch.setattr("tools.report.report", mock_report)

        from workflows.autocode_helpers.nodes.report import node_report

        state = {
            "trace_id": "test-autocode",
            "task": "Fix bug in parser",
            "task_type": "fix",
            "modified_files": ["core/parser.py"],
            "test_results": {"success": True, "passed": 5},
            "verification_notes": "All checks passed.",
            "commit_sha": "abc123",
        }

        result = node_report(state)

        assert result["trace_id"] == "test-autocode"
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["action"] == "report"
        assert call_kwargs["preset"] == "code_audit"
        assert "Code Audit" in call_kwargs["title"]
        assert "sections" in call_kwargs["config"]

    def test_node_report_best_effort_no_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        # Simulate report tool failure
        def failing_report(*args, **kwargs):
            raise RuntimeError("report tool failed")

        monkeypatch.setattr("tools.report.report", failing_report)

        from workflows.autocode_helpers.nodes.report import node_report

        state = {
            "trace_id": "test-autocode",
            "task": "Fix bug",
            "task_type": "fix",
            "modified_files": [],
            "test_results": {},
            "verification_notes": "",
            "commit_sha": "",
        }

        # Should not raise
        result = node_report(state)
        assert result["trace_id"] == "test-autocode"


class TestUnderstandReport:
    def test_node_report_generates_overview(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        mock_report = MagicMock()
        monkeypatch.setattr("tools.report.report", mock_report)

        from workflows.understand import node_report

        state = {
            "trace_id": "test-understand",
            "project_path": "D:\\mcp\\agent",
            "files_parsed": 42,
            "edges_created": 128,
            "errors": [],
        }

        import asyncio
        result = asyncio.run(node_report(state))

        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["action"] == "report"
        assert "Codebase Overview" in call_kwargs["title"]
        assert call_kwargs["preset"] == "code_audit"

    def test_node_report_with_errors(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        mock_report = MagicMock()
        monkeypatch.setattr("tools.report.report", mock_report)

        from workflows.understand import node_report

        state = {
            "trace_id": "test-understand",
            "project_path": "D:\\mcp\\agent",
            "files_parsed": 10,
            "edges_created": 30,
            "errors": ["Failed to parse core/parser.py: SyntaxError"],
        }

        import asyncio
        asyncio.run(node_report(state))

        mock_report.assert_called_once()
        config = mock_report.call_args.kwargs["config"]
        assert any(s["title"] == "Errors" for s in config["sections"])
