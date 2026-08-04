"""Tests for historical dashboard mode (v1.15 — sidebar groups + tooltips + trend lines)."""
from __future__ import annotations
import pytest
from skills.cvm.historical.modes.dashboard import dashboard

class TestDashboardMode:
    def test_dashboard_no_company(self):
        r = dashboard()
        assert r["status"] == "error"

    def test_dashboard_top_level_fields(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert r["status"] == "ok"
        assert "tabs" in r and "kpis" in r and "company_header" in r and "freshness_footer" in r

    def test_dashboard_tab_structure(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Valuation", "Profitability", "Ratio Grid", "Percentile Analysis"]
        groups = [t.get("group") for t in r["tabs"]]
        assert "Resumo" in groups and "Avaliação" in groups and "Análise" in groups

    def test_dashboard_top_level_kpis(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert len(r["kpis"]) == 8
        labels = [k["label"] for k in r["kpis"]]
        assert "P/L" in labels and "ROE" in labels and "Marg. Bruta" in labels

    def test_dashboard_valuation_has_subtabs(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        val_tab = next(t for t in r["tabs"] if t["name"] == "Valuation")
        assert val_tab["sections"][0]["type"] == "subtabs"
        sub_names = [st["name"] for st in val_tab["sections"][0]["tabs"]]
        assert "Percentil" in sub_names and "Tendência" in sub_names

    def test_dashboard_profitability_has_subtabs(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        prof_tab = next(t for t in r["tabs"] if t["name"] == "Profitability")
        assert prof_tab["sections"][0]["type"] == "subtabs"
        sub_names = [st["name"] for st in prof_tab["sections"][0]["tabs"]]
        assert "Percentil" in sub_names and "Tendência" in sub_names

    def test_dashboard_ratio_grid_has_tables(self, tmp_path, monkeypatch):
        """[v1.15] Ratio Grid is now split tables (not ratio_grid)."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        grid_tab = next(t for t in r["tabs"] if t["name"] == "Ratio Grid")
        # Should have at least 1 table section (Valuation or Rentabilidade)
        types = [s.get("type") for s in grid_tab["sections"]]
        assert "table" in types

    def test_dashboard_percentile_has_table(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        pct_tab = next(t for t in r["tabs"] if t["name"] == "Percentile Analysis")
        types = [s.get("type") for s in pct_tab["sections"]]
        assert "table" in types

def _patch_environment(tmp_path, monkeypatch):
    def mock_summary(company="", metric="lpa", months=60):
        return {"status": "ok", "company": company, "metric": metric,
                "current": {"value": 5.11, "date": "2024-06-30"},
                "percentiles": {"min": 3.0, "p25": 4.0, "median": 5.0, "p75": 6.0, "max": 8.0},
                "average": 5.0, "averages": {"1y": 4.5, "3y": 5.0, "5y": 5.2},
                "series": [{"date": "2024-06-30", "value": 5.11}]}
    monkeypatch.setattr("skills.cvm.historical.modes.dashboard.summary", mock_summary)
    monkeypatch.setattr("skills.cvm.historical.modes.dashboard.fetch_quartiles",
        lambda c, m, months=60: {"p25": 4.0, "median": 5.0, "p75": 6.0, "min": 3.0, "max": 8.0})
    monkeypatch.setattr("skills.cvm.historical.modes.dashboard.fetch_series",
        lambda c, m, months=60: [])
    monkeypatch.setattr("skills.cvm.historical.modes.dashboard.build_company_header",
        lambda c: {"ticker": c, "name": "TEST"})
    monkeypatch.setattr("skills.cvm.historical.modes.dashboard.build_price_chart",
        lambda c: None)
