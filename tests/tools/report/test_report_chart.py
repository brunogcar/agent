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


class TestMultiSeriesChart:
    """v1.2.2 — multi-series chart support."""

    def test_multi_series_config(self):
        data = {"x": ["Q1", "Q2", "Q3"],
                "datasets": [{"label": "A", "data": [1, 2, 3]},
                             {"label": "B", "data": [4, 5, 6]}]}
        cfg = charts._to_chartjs_config(data, "line", "Multi", {})
        assert cfg["type"] == "line"
        assert cfg["data"]["labels"] == ["Q1", "Q2", "Q3"]
        assert len(cfg["data"]["datasets"]) == 2
        assert cfg["data"]["datasets"][0]["label"] == "A"
        assert cfg["data"]["datasets"][0]["data"] == [1, 2, 3]
        assert cfg["data"]["datasets"][1]["label"] == "B"
        assert cfg["data"]["datasets"][1]["data"] == [4, 5, 6]

    def test_multi_series_distinct_colors(self):
        data = {"x": ["Q1"], "datasets": [{"label": "A", "data": [1]},
                                            {"label": "B", "data": [2]}]}
        cfg = charts._to_chartjs_config(data, "line", "T", {})
        c1 = cfg["data"]["datasets"][0]["borderColor"]
        c2 = cfg["data"]["datasets"][1]["borderColor"]
        assert c1 != c2  # distinct colors

    def test_single_series_still_works(self):
        """Backward compat: {"x":[], "y":[]} still produces 1 dataset."""
        cfg = charts._to_chartjs_config({"x": ["A", "B"], "y": [1, 2]}, "bar", "T", {})
        assert len(cfg["data"]["datasets"]) == 1
        assert cfg["data"]["datasets"][0]["data"] == [1, 2]


class TestCandlestickChart:
    """v1.2.6 — candlestick chart support."""

    def test_candlestick_config_shape(self):
        """v1.2.8: candlestick rendered as native bar chart (floating bar).
        Each bar = [low, high], colored green/red by open vs close."""
        data = {"_candlestick": True, "ohlc_data": [
            {"t": "2025-07-01", "o": 38.0, "h": 38.5, "l": 37.8, "c": 38.2},
            {"t": "2025-07-02", "o": 38.2, "h": 38.6, "l": 38.1, "c": 38.5},
        ]}
        cfg = charts._to_chartjs_config(data, "candlestick", "PETR4", {})
        assert cfg["type"] == "bar"  # v1.2.8: native bar, not candlestick plugin
        assert len(cfg["data"]["datasets"]) == 1
        assert len(cfg["data"]["datasets"][0]["data"]) == 2
        # Each data point = [low, high] (floating bar)
        assert cfg["data"]["datasets"][0]["data"][0] == [37.8, 38.5]  # [low, high]
        # Green (close >= open) for first point (38.2 >= 38.0)
        assert cfg["data"]["datasets"][0]["backgroundColor"][0] == "#22c55e"

    def test_candlestick_not_triggered_for_regular_dict(self):
        """Regular dicts (no _candlestick key) must NOT use candlestick path."""
        cfg = charts._to_chartjs_config({"x": ["A"], "y": [1]}, "line", "T", {})
        assert cfg["type"] == "line"  # not candlestick
