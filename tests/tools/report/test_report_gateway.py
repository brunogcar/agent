"""
tests/tools/report/test_report_gateway.py -- Gateway + metrics.json tests.
"""
import json
import pytest
from pathlib import Path


class TestMetricsJson:
    def test_write_metrics_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        from tools.report_core.html import _write_metrics

        _write_metrics(
            trace_id="test-metrics",
            action="dashboard",
            title="Test Dashboard",
            files=["test.html"],
            config={"preset": "financial", "theme": "dark", "accent": "#0d9488"},
        )

        metrics_path = tmp_path / "reports" / "test-metrics" / "metrics.json"
        assert metrics_path.exists()

        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert data["trace_id"] == "test-metrics"
        assert data["action"] == "dashboard"
        assert data["title"] == "Test Dashboard"
        assert data["files_count"] == 1
        assert data["preset"] == "financial"
        assert data["theme"] == "dark"
        assert data["accent"] == "#0d9488"
        assert "created_at" in data

    def test_metrics_has_data_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        from tools.report_core.html import _write_metrics

        _write_metrics(
            trace_id="test-data",
            action="report",
            title="With Data",
            files=["x.html"],
            config={"sections": [{"title": "A"}]},
        )

        metrics_path = tmp_path / "reports" / "test-data" / "metrics.json"
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert data["has_data"] is True

    def test_metrics_no_data_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)

        from tools.report_core.html import _write_metrics

        _write_metrics(
            trace_id="test-empty",
            action="report",
            title="Empty",
            files=["x.html"],
            config={},
        )

        metrics_path = tmp_path / "reports" / "test-empty" / "metrics.json"
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert data["has_data"] is False


class TestGateway:
    def test_list_reports_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.agent_root", str(tmp_path))

        from core.gateway_backend.routes.reports import _list_reports
        assert _list_reports() == []

    def test_list_reports_with_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.agent_root", str(tmp_path))

        report_dir = tmp_path / "reports" / "trace-123"
        report_dir.mkdir(parents=True)
        manifest = {
            "trace_id": "trace-123",
            "action": "dashboard",
            "title": "Test Report",
            "created_at": "2026-06-11T20:00:00+0000",
            "files": ["test.html"],
            "preset": "code_audit",
            "theme": "dark",
        }
        (report_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        metrics = {"trace_id": "trace-123", "files_count": 1}
        (report_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

        from core.gateway_backend.routes.reports import _list_reports
        reports = _list_reports()
        assert len(reports) == 1
        assert reports[0]["trace_id"] == "trace-123"
        assert reports[0]["title"] == "Test Report"
        assert reports[0]["metrics"]["files_count"] == 1

    def test_logs_dir_explicit(self, monkeypatch):
        from core.gateway_backend.routes.reports import _logs_dir
        assert "logs" in str(_logs_dir()) and "agent" in str(_logs_dir())
