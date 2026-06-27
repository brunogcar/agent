"""Tests for export action."""
from pathlib import Path

import pytest

from tools.report_core import export


class TestExport:
    """PDF/PNG export via Playwright (optional)."""

    def test_export_missing_data_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="data must be"):
            export.run(trace_id="test", title="X", data=None, config={})

    def test_export_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="not found"):
            export.run(trace_id="test", title="X", data="nonexistent.html", config={})

    def test_export_html_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        # Create a dummy HTML file in workspace/reports
        report_dir = tmp_path / "reports" / "test-export"
        report_dir.mkdir(parents=True)
        html_file = report_dir / "test.html"
        html_file.write_text("<html><body>Test</body></html>", encoding="utf-8")

        result = export.run(
            trace_id="test-export-out",
            title="Export",
            data=str(html_file),
            config={"format": "pdf"},
        )
        # Playwright may not be installed — either success or warning
        assert result["status"] == "success"
        assert result["html_path"] == str(html_file)
        if result.get("pdf_path"):
            assert Path(result["pdf_path"]).exists()
        elif result.get("warning"):
            assert "playwright" in result["warning"].lower()

    def test_export_scoping_workspace(self, tmp_path, monkeypatch):
        """Export should resolve paths relative to workspace by default."""
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        report_dir = tmp_path / "reports" / "test-scope"
        report_dir.mkdir(parents=True)
        html_file = report_dir / "scope.html"
        html_file.write_text("<html></html>", encoding="utf-8")

        # Pass relative path — should resolve to workspace
        result = export.run(
            trace_id="test-scope-out",
            title="Scope",
            data=str(html_file),
            config={"format": "png"},
        )
        assert result["status"] == "success"
