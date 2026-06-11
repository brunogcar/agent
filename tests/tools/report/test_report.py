"""
tests/tools/report/test_report.py - Report tool tests.
"""

import json
from pathlib import Path
import pathlib

import pytest

from tools.report_core._registry import DISPATCH, DISPATCH_METADATA, PRESETS
from tools.report_core.contracts import report_ok, report_fail
from tools.report_core.paths import report_out_dir
from tools.report_core.data import load_data

class TestRegistry:
    def test_dispatch_keys(self):
        assert set(DISPATCH.keys()) == {"chart", "map", "report", "dashboard", "diagram", "export", "compare", "timeline", "scorecard"}

    def test_metadata_covers_all_actions(self):
        assert set(DISPATCH_METADATA.keys()) == set(DISPATCH.keys())

    def test_presets_exist(self):
        assert set(PRESETS.keys()) == {"financial", "code_audit", "research", "system_health", "compare", "timeline", "scorecard"}

class TestContracts:
    def test_report_ok_injects_trace_id(self):
        r = report_ok({"html_path": "/tmp/x.html"}, trace_id="abc123")
        assert r["status"] == "success"
        assert r["trace_id"] == "abc123"
        assert r["html_path"] == "/tmp/x.html"

    def test_report_fail_injects_trace_id(self):
        r = report_fail("boom", trace_id="abc123")
        assert r["status"] == "error"
        assert r["trace_id"] == "abc123"
        assert "boom" in r["error"]

class TestPaths:
    def test_report_out_dir_returns_path(self, tmp_path, monkeypatch):
        from core.config import cfg
        monkeypatch.setattr(cfg, "workspace_root", tmp_path)
        d = report_out_dir("test-trace-123")
        assert d.exists()
        assert d.name == "test-trace-123"
        assert d.parent.name == "reports"

class TestDataLoader:
    def test_inline_data(self):
        data, err = load_data(data={"x": [1, 2], "y": [3, 4]})
        assert err == ""
        assert data == {"x": [1, 2], "y": [3, 4]}

    def test_no_data_or_path(self):
        data, err = load_data()
        assert data is None
        assert "Provide either" in err

    def test_url_blocked(self):
        data, err = load_data(data_path="http://evil.com/data.csv")
        assert data is None
        assert "local file path" in err

    def test_https_blocked(self):
        data, err = load_data(data_path="https://example.com/data.json")
        assert data is None
        assert "local file path" in err

    def test_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.data.resolve_path", lambda p: (pathlib.Path(p), ""))
        p = tmp_path / "test.json"
        p.write_text(json.dumps({"a": 1}), encoding="utf-8")
        data, err = load_data(data_path=str(p))
        assert err == ""
        assert data == {"a": 1}

    def test_csv_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.data.resolve_path", lambda p: (pathlib.Path(p), ""))
        p = tmp_path / "test.csv"
        csv_lines = ["name,value", "foo,1", "bar,2"]
        p.write_text("\n".join(csv_lines), encoding="utf-8")
        data, err = load_data(data_path=str(p))
        assert err == ""
        assert hasattr(data, "columns") # pandas DataFrame

    def test_unsupported_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.data.resolve_path", lambda p: (pathlib.Path(p), ""))
        p = tmp_path / "test.txt"
        p.write_text("hello", encoding="utf-8")
        data, err = load_data(data_path=str(p))
        assert data is None
        assert "Unsupported" in err

class TestChartsBuilder:
    def test_generate_palette(self):
        from tools.report_core.charts import _generate_palette
        pal = _generate_palette(5, "#0d9488")
        assert len(pal) == 5
        assert len(set(pal)) == 5 # distinct colors

    def test_chartjs_config_bar(self):
        from tools.report_core.charts import _to_chartjs_config
        cfg = _to_chartjs_config({"x": ["A", "B"], "y": [1, 2]}, "bar", "Test", {})
        assert cfg["type"] == "bar"
        assert cfg["data"]["labels"] == ["A", "B"]
        assert cfg["data"]["datasets"][0]["data"] == [1, 2]

    def test_chartjs_config_pie(self):
        from tools.report_core.charts import _to_chartjs_config
        cfg = _to_chartjs_config({"labels": ["A", "B"], "values": [1, 2]}, "pie", "Test", {})
        assert cfg["type"] == "pie"
        assert len(cfg["data"]["datasets"][0]["backgroundColor"]) == 2

class TestDiagramsBuilder:
    def test_dict_to_mermaid(self):
        from tools.report_core.diagrams import _dict_to_mermaid
        src = _dict_to_mermaid({
            "nodes": [{"id": "A", "label": "Start"}, {"id": "B", "label": "End"}],
            "edges": [{"from": "A", "to": "B"}]
        }, "flowchart")
        assert "A[Start]" in src
        assert "B[End]" in src
        assert "A --> B" in src

class TestHtmlRenderer:
    def test_render_template_creates_file(self, tmp_path):
        from tools.report_core.html import render_template
        out = tmp_path / "out.html"
        render_template("report.html", {"title": "T", "sections": [], "kpis": [], "sources": [], "theme": "dark", "trace_id": ""}, out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "T" in content
