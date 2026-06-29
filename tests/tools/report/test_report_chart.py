"""Tests for chart builder and template rendering."""
from pathlib import Path

import pytest

from tools.report_ops import charts
from tools.report_ops.paths import report_out_dir


class TestChartBuilder:
    """Chart.js configuration builders."""

    def test_generate_palette(self):
        pal = charts._generate_palette(5, "#0d9488")
        assert len(pal) == 5
        assert len(set(pal)) == 5  # distinct colors

    def test_generate_palette_exceeds_base(self):
        """When n > 10, colors repeat (documented behavior)."""
        pal = charts._generate_palette(15, "#0d9488")
        assert len(pal) == 15
        assert len(set(pal)) < 15  # some repeats

    def test_generate_palette_base_param_accepted(self):
        """base parameter is accepted but currently unused (reserved)."""
        pal = charts._generate_palette(3, "#ff0000")
        assert len(pal) == 3

    def test_chartjs_config_bar(self):
        cfg = charts._to_chartjs_config({"x": ["A", "B"], "y": [1, 2]}, "bar", "Test", {})
        assert cfg["type"] == "bar"
        assert cfg["data"]["labels"] == ["A", "B"]
        assert cfg["data"]["datasets"][0]["data"] == [1, 2]

    def test_chartjs_config_pie(self):
        cfg = charts._to_chartjs_config({"labels": ["A", "B"], "values": [1, 2]}, "pie", "Test", {})
        assert cfg["type"] == "pie"
        assert len(cfg["data"]["datasets"][0]["backgroundColor"]) == 2

    def test_chartjs_config_list_data(self):
        cfg = charts._to_chartjs_config([10, 20, 30], "line", "List", {})
        assert cfg["data"]["labels"] == [0, 1, 2]
        assert cfg["data"]["datasets"][0]["data"] == [10, 20, 30]

    def test_build_creates_html(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        result = charts.build(
            trace_id="test-chart",
            title="Revenue",
            data={"x": ["Q1", "Q2"], "y": [100, 150]},
            config={"chart_type": "bar"},
        )
        assert result["type"] == "chart"
        assert result["title"] == "Revenue"
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Revenue" in content
        assert "chart.js" in content.lower() or "Chart" in content

    def test_build_no_data_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError):
            charts.build(
                trace_id="test-empty",
                title="Empty",
                data=None,
                config={},
            )
