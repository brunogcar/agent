"""Real integration tests — no mocking, real file I/O, real path_guard.

These tests use actual resolve_path and write to tmp_path.
They verify the full stack: facade → action → builder → template → filesystem.
"""
import json
from pathlib import Path

import pytest

from tools.report import report


class TestRealIntegration:
    """End-to-end report generation with real filesystem."""

    def test_real_chart_generation(self, tmp_path, monkeypatch):
        """Generate a real chart HTML file via the facade."""
        monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)

        result = report(
            action="chart",
            title="Real Chart",
            data={"x": ["A", "B", "C"], "y": [10, 20, 30]},
            config={"chart_type": "bar", "theme": "dark"},
            trace_id="real-chart-001",
        )
        assert result["status"] == "success"
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Real Chart" in content

    def test_real_list_action(self):
        """List action requires no filesystem — pure registry lookup."""
        result = report(action="list", trace_id="real-list-001")
        assert result["status"] == "success"
        assert result["count"] == 11

    def test_real_help_action(self):
        """Help action requires no filesystem — pure metadata lookup."""
        result = report(action="help", data="dashboard", trace_id="real-help-001")
        assert result["status"] == "success"
        assert result["action"] == "dashboard"
        assert "description" in result

    def test_real_compare_generation(self, tmp_path, monkeypatch):
        """Generate a real comparison report via the facade."""
        monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)

        result = report(
            action="compare",
            title="Real Compare",
            data={"before": {"price": 100}, "after": {"price": 120}},
            config={"theme": "dark"},
            trace_id="real-compare-001",
        )
        assert result["status"] == "success"
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Real Compare" in content
        assert "20.00" in content

    def test_real_timeline_generation(self, tmp_path, monkeypatch):
        """Generate a real timeline report via the facade."""
        monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)

        result = report(
            action="timeline",
            title="Real Timeline",
            data=[{"label": "M1", "start": "2026-01-01", "end": "2026-01-31", "status": "done"}],
            config={},
            trace_id="real-timeline-001",
        )
        assert result["status"] == "success"
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Real Timeline" in content
        assert "M1" in content

    def test_real_scorecard_generation(self, tmp_path, monkeypatch):
        """Generate a real scorecard report via the facade."""
        monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)

        result = report(
            action="scorecard",
            title="Real Scorecard",
            data=[{"name": "CPU", "score": 85, "target": 90, "weight": 1.0}],
            config={"theme": "dark"},
            trace_id="real-scorecard-001",
        )
        assert result["status"] == "success"
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Real Scorecard" in content

    def test_preset_applied_in_facade(self, tmp_path, monkeypatch):
        """Verify preset merges correctly through the facade."""
        monkeypatch.setattr("core.config.cfg.workspace_root", tmp_path)
        monkeypatch.setattr("core.config.cfg.agent_root", tmp_path)

        result = report(
            action="chart",
            title="Preset Test",
            data={"x": ["A"], "y": [1]},
            preset="financial",
            config={"chart_type": "bar"},
            trace_id="real-preset-001",
        )
        assert result["status"] == "success"
        # The file should exist — preset was applied before dispatch
        html_path = tmp_path / "reports" / "real-preset-001" / "Preset_Test.html"
        assert html_path.exists()
