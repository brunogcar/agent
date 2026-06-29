"""Tests for compare builder."""
from pathlib import Path

import pytest

from tools.report_ops import compare


class TestCompare:
    """Side-by-side diff table builder."""

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

    def test_diff_dicts_unchanged(self):
        before = {"a": 1}
        after = {"a": 1}
        rows = compare._diff_dicts(before, after)
        assert rows[0]["delta_class"] == "neu"
        assert rows[0]["delta"] == "—"

    def test_build_dict_compare(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
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
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
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
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="compare requires"):
            compare.build(trace_id="test-missing", title="X", data={"before": {}}, config={})

    def test_build_unsupported_types_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="Unsupported compare types"):
            compare.build(trace_id="test-bad", title="X", data={"before": "string", "after": 123}, config={})
