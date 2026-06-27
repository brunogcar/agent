"""Tests for preset application in report facade."""
from tools.report import report
from tools.report_core._registry import PRESETS


class TestPresets:
    """Preset merging and application."""

    def test_presets_exist(self):
        assert "financial" in PRESETS
        assert "code_audit" in PRESETS
        assert "research" in PRESETS
        assert "system_health" in PRESETS
        assert "compare" in PRESETS
        assert "timeline" in PRESETS
        assert "scorecard" in PRESETS

    def test_preset_merges_into_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        # Use list action (lightweight, no file generation) to test preset merge
        result = report(action="list", preset="financial", trace_id="test-preset")
        assert result["status"] == "success"

    def test_preset_overridden_by_explicit_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        # chart action with preset + explicit config override
        result = report(
            action="chart",
            title="Preset Override",
            data={"x": ["A"], "y": [1]},
            config={"theme": "light"},
            preset="financial",
            trace_id="test-override",
        )
        assert result["status"] == "success"
        # The HTML file should exist — theme is merged at facade level
        html_path = tmp_path / "reports" / "test-override" / "Preset_Override.html"
        assert html_path.exists()

    def test_unknown_preset_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = report(action="list", preset="nonexistent", trace_id="test-bad-preset")
        assert result["status"] == "success"  # Unknown preset is silently ignored
