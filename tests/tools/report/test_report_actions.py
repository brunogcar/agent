"""
tests/tools/report/test_report_actions.py — Phase 3: compare, timeline, scorecard.
"""

import json
import pytest
from pathlib import Path

from tools.report_core import compare, timeline, scorecard
from tools.report_core.paths import report_out_dir


class TestCompare:
    def test_diff_dicts_basic(self):
        before = {"price": 100, "volume": 500, "name": "ABC"}
        after = {"price": 120, "volume": 500, "name": "ABC", "pe": 15}
        rows = compare._diff_dicts(before, after)
        assert len(rows) == 4
        price_row = [r for r in rows if r["key"] == "price"][0]
        assert price_row["delta_class"] == "pos"
        assert "+20.00" in price_row["delta"]
        vol_row = [r for r in rows if r["key"] == "volume"][0]
        assert vol_row["delta_class"] == "neu"
        pe_row = [r for r in rows if r["key"] == "pe"][0]
        assert pe_row["delta_class"] == "pos"
        assert pe_row["before"] == "—"

    def test_diff_dicts_numeric_negative(self):
        before = {"revenue": 1000}
        after = {"revenue": 800}
        rows = compare._diff_dicts(before, after)
        assert rows[0]["delta_class"] == "neg"
        assert "-200.00" in rows[0]["delta"]

    def test_build_dict_compare(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = compare.build(
            trace_id="test-compare", title="Price Change",
            data={"before": {"price": 100}, "after": {"price": 120}},
            config={"theme": "dark"},
        )
        assert result["type"] == "compare"
        assert result["mode"] == "dict"
        assert result["rows"] == 1
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Price Change" in content
        assert "20.00" in content

    def test_build_table_compare(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        before = [{"ticker": "PETR4", "price": 30}, {"ticker": "VALE3", "price": 65}]
        after = [{"ticker": "PETR4", "price": 32}, {"ticker": "VALE3", "price": 63}]
        result = compare.build(
            trace_id="test-table", title="Portfolio Delta",
            data={"before": before, "after": after},
            config={"key_col": "ticker", "theme": "dark"},
        )
        assert result["type"] == "compare"
        assert result["mode"] == "table"
        assert Path(result["html_path"]).exists()

    def test_build_missing_data_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="compare requires"):
            compare.build(trace_id="test-missing", title="X", data={"before": {}}, config={})


class TestTimeline:
    def test_parse_date(self):
        d = timeline._parse_date("2026-06-15")
        assert d.year == 2026 and d.month == 6 and d.day == 15

    def test_build_svg_contains_events(self):
        events = [
            {"label": "Phase 1", "start": "2026-01-01", "end": "2026-02-15", "status": "done"},
            {"label": "Phase 2", "start": "2026-02-16", "end": "2026-04-01", "status": "active"},
        ]
        svg = timeline._build_svg(events)
        assert "<svg" in svg and "Phase 1" in svg and "Phase 2" in svg

    def test_build(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        events = [{"label": "MVP", "start": "2026-01-01", "end": "2026-03-01", "status": "done"}]
        result = timeline.build(trace_id="test-timeline", title="Roadmap", data=events, config={"theme": "dark"})
        assert result["type"] == "timeline" and result["events"] == 1
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Roadmap" in content and "<svg" in content

    def test_build_empty_events_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="timeline requires"):
            timeline.build("test", "X", [], {})


class TestScorecard:
    def test_rag_status(self):
        assert scorecard._rag_status(95, 90) == "green"
        assert scorecard._rag_status(75, 90) == "amber"
        assert scorecard._rag_status(50, 90) == "red"

    def test_rag_color(self):
        assert scorecard._rag_color("green", "dark") == "#22c55e"
        assert scorecard._rag_color("red", "light") == "#dc2626"

    def test_build_radar_config(self):
        dims = [{"name": "Security", "score": 85, "target": 95}, {"name": "Speed", "score": 72, "target": 80}]
        cfg = scorecard._build_radar_config(dims)
        assert cfg["type"] == "radar"
        assert cfg["data"]["labels"] == ["Security", "Speed"]
        assert cfg["data"]["datasets"][0]["label"] == "Current"
        assert cfg["data"]["datasets"][1]["label"] == "Target"

    def test_build(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        dims = [
            {"name": "Security", "score": 85, "target": 95, "weight": 0.3},
            {"name": "Speed", "score": 72, "target": 80, "weight": 0.3},
            {"name": "Reliability", "score": 60, "target": 90, "weight": 0.4},
        ]
        result = scorecard.build(trace_id="test-scorecard", title="System Health", data=dims, config={"theme": "dark"})
        assert result["type"] == "scorecard" and result["dimensions"] == 3 and "overall_score" in result
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "System Health" in content and "radarChart" in content
        manifest_path = report_out_dir("test-scorecard") / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["action"] == "scorecard"

    def test_build_empty_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="scorecard requires"):
            scorecard.build("test", "X", [], {})
