"""Tests for report output path resolution."""
from pathlib import Path

from tools.report_ops.paths import report_out_dir, report_manifest_path


class TestPaths:
    """Output path resolution with path guard."""

    def test_report_out_dir_returns_path(self, tmp_path, monkeypatch):
        from core.config import cfg
        monkeypatch.setattr(cfg, "workspace_root", tmp_path)
        d = report_out_dir("test-trace-123")
        assert d.exists()
        assert d.name == "test-trace-123"
        assert d.parent.name == "reports"

    def test_report_out_dir_sanitizes_trace_id(self, tmp_path, monkeypatch):
        from core.config import cfg
        monkeypatch.setattr(cfg, "workspace_root", tmp_path)
        d = report_out_dir("trace/with\bad:chars")
        assert d.exists()
        assert "_" in d.name
        assert "/" not in d.name
        assert "\\" not in d.name
        assert ":" not in d.name

    def test_report_manifest_path(self, tmp_path, monkeypatch):
        from core.config import cfg
        monkeypatch.setattr(cfg, "workspace_root", tmp_path)
        p = report_manifest_path("trace-456")
        assert p.name == "manifest.json"
        assert p.parent.name == "trace-456"
        assert p.parent.parent.name == "reports"
