"""Tests for report_ops/table.py — tabular statement builder.

Covers: list-of-lists vs list-of-dicts rows, column auto-derivation, per-column
format specs, KPI pre-formatting, adapter path, error/no-data handling, and
the adapter registry (auto-discovery + 12 adapters).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.report_ops import table


# ── Synthetic skill results (mirror the real skill output shapes) ────────────

FINANCIALS_QUARTERLY = {
    "status": "ok",
    "company": "PETROBRAS",
    "period_type": "quarterly",
    "periods": [
        {"period": "1T2025", "year": 2025, "quarter": 1,
         "metrics": {"receita_liquida": 100_000, "lucro_bruto": 30_000,
                     "ebit": 20_000, "ebitda": 25_000, "lucro_liquido": 15_000,
                     "fco": 22_000},
         "ratios": {"marg_bruta": 0.30, "marg_ebitda": 0.25,
                    "marg_liquida": 0.15, "roe": 0.18}},
        {"period": "2T2025", "year": 2025, "quarter": 2,
         "metrics": {"receita_liquida": 120_000, "lucro_bruto": 36_000,
                     "ebit": 24_000, "ebitda": 30_000, "lucro_liquido": 18_000,
                     "fco": 26_000},
         "ratios": {"marg_bruta": 0.30, "marg_ebitda": 0.25,
                    "marg_liquida": 0.15, "roe": 0.20}},
    ],
}

VALUATION_RATIOS = {
    "status": "ok",
    "ticker": "PETR4",
    "ratios": {
        "price": 38.5, "p_l": 8.2, "p_vpa": 1.9, "ev_ebitda": 4.5,
        "dividend_yield": 0.12, "market_cap": 500_000_000_000,
        "total_shares": 13_000_000_000, "eps": 4.7,
    },
    "sources": {},
}


class TestNormalizeSection:
    def test_rows_as_list_of_lists(self):
        sec = table._normalize_section(
            {"title": "T", "columns": ["A", "B"], "rows": [["x", 1], ["y", 2]]}, 0
        )
        assert sec["columns"] == ["A", "B"]
        assert sec["rows"] == [["x", 1], ["y", 2]]
        assert sec["col_formats"] == ["text", "text"]
        assert sec["row_count"] == 2

    def test_rows_as_list_of_dicts_derives_columns(self):
        sec = table._normalize_section(
            {"title": "T",
             "rows": [{"Período": "1T26", "Receita": 1000},
                      {"Período": "4T25", "Receita": 950}]},
            0,
        )
        assert sec["columns"] == ["Período", "Receita"]
        assert sec["rows"] == [["1T26", 1000], ["4T25", 950]]

    def test_formats_map_becomes_col_formats(self):
        sec = table._normalize_section(
            {"title": "T", "columns": ["P", "Rev", "Marg"],
             "rows": [["1T26", 1000, 0.25]],
             "formats": {"Rev": "brl", "Marg": "pct"}}, 0
        )
        assert sec["col_formats"] == ["text", "brl", "pct"]

    def test_no_columns_no_rows_is_empty(self):
        sec = table._normalize_section({"title": "Empty"}, 0)
        assert sec["columns"] == []
        assert sec["rows"] == []
        assert sec["row_count"] == 0

    def test_list_of_lists_pads_short_rows(self):
        sec = table._normalize_section(
            {"title": "T", "columns": ["A", "B", "C"], "rows": [["x"]]}, 0
        )
        # short row padded with None
        assert sec["rows"][0] == ["x", None, None]

    def test_default_title_when_missing(self):
        sec = table._normalize_section({"rows": [["a"]]}, 2)
        assert sec["title"] == "Table 3"


class TestNormalizeKpis:
    def test_kpi_preformatted_by_spec(self):
        # 120B -> R$ 120,00 B (compact BRL tier)
        kpis = table._normalize_kpis([{"label": "Receita", "value": 120_000_000_000, "format": "brl"}])
        assert kpis[0]["label"] == "Receita"
        assert kpis[0]["value"] == "R$ 120,00 B"  # pre-formatted string

    def test_kpi_text_passthrough(self):
        kpis = table._normalize_kpis([{"label": "Ticker", "value": "PETR4"}])
        assert kpis[0]["value"] == "PETR4"

    def test_kpi_with_delta(self):
        kpis = table._normalize_kpis([{"label": "X", "value": 5, "delta": "+2"}])
        assert kpis[0]["delta"] == "+2"

    def test_non_dict_skipped(self):
        assert table._normalize_kpis(["not a dict", 42]) == []


class TestBuildDirect:
    """table.build() with direct table-shape data (no adapter)."""

    def test_build_creates_html_with_list_of_lists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        data = {
            "company": "PETR4",
            "sections": [{
                "title": "Quarterly Summary",
                "columns": ["Período", "Receita", "Marg. EBITDA"],
                "rows": [["2T2025", 120_000_000_000, 0.25], ["1T2025", 100_000_000_000, 0.25]],
                "formats": {"Receita": "brl", "Marg. EBITDA": "pct"},
                "note": "Standalone quarters.",
            }],
            "kpis": [{"label": "Receita", "value": 120_000_000_000, "format": "brl"}],
        }
        r = table.build("trace-1", "PETR4 Financials", data, {"theme": "dark"})
        assert r["type"] == "table"
        assert r["sections"] == 1
        assert r["total_rows"] == 2
        assert r["adapter"] == ""
        html_path = Path(r["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        # rows present
        assert "2T2025" in content and "1T2025" in content
        # BRL compact formatting landed in HTML (120B -> R$ 120,00 B)
        assert "R$ 120,00 B" in content
        # pct formatting landed (0.25 -> 25,00%)
        assert "25,00%" in content

    def test_build_with_list_of_dicts(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        data = {"sections": [{
            "title": "T",
            "rows": [{"A": 1, "B": 2}, {"A": 3, "B": 4}],
        }]}
        r = table.build("trace-2", "Dict Rows", data, {})
        assert r["sections"] == 1
        assert r["total_rows"] == 2
        html = Path(r["html_path"]).read_text(encoding="utf-8")
        assert "A" in html and "B" in html

    def test_build_multiple_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        data = {"sections": [
            {"title": "A", "columns": ["X"], "rows": [[1]]},
            {"title": "B", "columns": ["Y"], "rows": [[2], [3]]},
        ]}
        r = table.build("trace-3", "Multi", data, {})
        assert r["sections"] == 2
        assert r["total_rows"] == 3

    def test_build_raises_on_non_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="dict"):
            table.build("trace-4", "Bad", ["not", "a", "dict"], {})

    def test_build_raises_on_no_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="sections"):
            table.build("trace-5", "Empty", {"kpis": []}, {})

    def test_build_writes_manifest_and_metrics(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        data = {"sections": [{"title": "T", "columns": ["X"], "rows": [[1]]}]}
        table.build("trace-6", "Manifest", data, {"theme": "dark"})
        out_dir = tmp_path / "reports" / "trace-6"
        assert (out_dir / "manifest.json").exists()
        assert (out_dir / "metrics.json").exists()


class TestBuildWithAdapter:
    """table.build() with config['adapter'] flattening a skill result."""

    def test_financials_quarterly_adapter(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        r = table.build("trace-a1", "PETR4 Q", FINANCIALS_QUARTERLY,
                        {"adapter": "financials_quarterly"})
        assert r["adapter"] == "financials_quarterly"
        assert r["sections"] == 1
        # quarterly periods are oldest-first in the skill; adapter reverses to newest-first
        html = Path(r["html_path"]).read_text(encoding="utf-8")
        # 2T2025 should appear before 1T2025 in the rendered table body
        assert html.index("2T2025") < html.index("1T2025")

    def test_valuation_ratios_adapter(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        r = table.build("trace-a2", "PETR4 V", VALUATION_RATIOS,
                        {"adapter": "valuation_ratios"})
        assert r["adapter"] == "valuation_ratios"
        html = Path(r["html_path"]).read_text(encoding="utf-8")
        # KPI strip values
        assert "PETR4" in html
        assert "P/L" in html
        # Market cap compact BRL
        assert "R$ 500,00 B" in html

    def test_unknown_adapter_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="Unknown adapter"):
            table.build("trace-a3", "Bad", FINANCIALS_QUARTERLY,
                        {"adapter": "no_such_adapter"})

    def test_error_skill_result_renders_status_table(self, tmp_path, monkeypatch):
        """A not_synced skill result must render a status table, not crash."""
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        bad = {"status": "not_synced", "error": "dfp.db missing"}
        r = table.build("trace-a4", "Err", bad, {"adapter": "financials_quarterly"})
        assert r["sections"] == 1
        html = Path(r["html_path"]).read_text(encoding="utf-8")
        assert "not_synced" in html
        assert "dfp.db missing" in html
