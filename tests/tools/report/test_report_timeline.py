"""Tests for timeline builder."""
from pathlib import Path

import pytest

from tools.report_ops import timeline


class TestTimeline:
    """SVG Gantt/timeline builder."""

    def test_parse_date(self):
        d = timeline._parse_date("2026-06-15")
        assert d.year == 2026 and d.month == 6 and d.day == 15

    def test_build_svg_contains_events(self):
        events = [
            {"label": "Phase 1", "start": "2026-01-01", "end": "2026-02-15", "status": "done"},
            {"label": "Phase 2", "start": "2026-02-16", "end": "2026-04-01", "status": "active"},
        ]
        svg = timeline._build_svg(events)
        assert "Phase 1" in svg
        assert "Phase 2" in svg
        assert "<svg" in svg

    def test_build_svg_empty_events(self):
        svg = timeline._build_svg([])
        assert "No timeline events" in svg

    def test_build_svg_invalid_dates(self):
        events = [{"label": "Bad", "start": "not-a-date", "end": "2026-01-01"}]
        svg = timeline._build_svg(events)
        assert "Invalid date format" in svg

    def test_escape_svg(self):
        assert timeline._escape_svg("A & B") == "A &amp; B"
        assert timeline._escape_svg("<tag>") == "&lt;tag&gt;"

    def test_build_creates_html(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        result = timeline.build(
            trace_id="test-timeline",
            title="Project Plan",
            data=[{"label": "Phase 1", "start": "2026-01-01", "end": "2026-02-15", "status": "done"}],
            config={},
        )
        assert result["type"] == "timeline"
        assert result["events"] == 1
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Project Plan" in content
        assert "Phase 1" in content

    def test_build_missing_data_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="timeline requires"):
            timeline.build(trace_id="test-missing", title="X", data=[], config={})
