"""Tests for HTML renderer, atomic writes, and builder outputs."""
import json
from pathlib import Path

import pytest

from tools.report_core import html


class TestHtmlRenderer:
    """Jinja2 renderer with atomic writes."""

    def test_render_template_creates_file(self, tmp_path):
        out = tmp_path / "out.html"
        html.render_template("report.html", {
            "title": "Test Title", 
            "sections": [{"title": "Hello", "text": "World"}],
            "kpis": [{"label": "K1", "value": "V1"}],
            "sources": [],
            "theme": "dark", "trace_id": "", "accent": "#0d9488",
        }, out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        # Should contain rendered content from sections or kpis
        assert "Hello" in content or "K1" in content or "Test Title" in content

    def test_render_template_atomic_write(self, tmp_path):
        """Atomic write should not leave temp files behind."""
        out = tmp_path / "atomic.html"
        html.render_template("report.html", {
            "title": "Atomic", 
            "sections": [{"title": "Sec", "text": "Body"}],
            "kpis": [], "sources": [],
            "theme": "dark", "trace_id": "", "accent": "#0d9488",
        }, out)
        # No .tmp file should exist
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0
        assert out.exists()

    def test_build_report_creates_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = html.build_report(
            trace_id="test-report",
            title="Q3 Analysis",
            data={"revenue": 150},
            config={"sections": [{"title": "Overview", "text": "Strong quarter"}]},
        )
        assert result["type"] == "report"
        assert Path(result["html_path"]).exists()

        manifest_path = tmp_path / "reports" / "test-report" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["trace_id"] == "test-report"
        assert manifest["action"] == "report"

    def test_build_report_creates_metrics(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        html.build_report(
            trace_id="test-metrics",
            title="Metrics Test",
            data={"x": 1},
            config={"sections": [{"title": "A"}]},
        )
        metrics_path = tmp_path / "reports" / "test-metrics" / "metrics.json"
        assert metrics_path.exists()
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert metrics["files_count"] == 1
        assert metrics["has_data"] is True

    def test_build_dashboard(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = html.build_dashboard(
            trace_id="test-dash",
            title="Dashboard",
            data={"x": 1},
            config={"tabs": [{"title": "Tab1"}], "kpis": [], "charts": []},
        )
        assert result["type"] == "dashboard"
        assert result["tabs"] == 1
        assert Path(result["html_path"]).exists()

    def test_build_dashboard_no_data_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        html.build_dashboard(
            trace_id="test-empty-dash",
            title="Empty",
            data={},
            config={},
        )
        metrics_path = tmp_path / "reports" / "test-empty-dash" / "metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert metrics["has_data"] is False
