"""Tests for historical dashboard mode.

[v5] Simplified — consolidated 8 tests into 2 to reduce runtime.
Each dashboard() call takes ~0.4s with mocks, so 8 calls = 3.2s.
Now 2 calls = 0.8s.
"""
from __future__ import annotations
import pytest
from skills.cvm.historical.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_company(self):
        """Empty company → error."""
        r = dashboard()
        assert r["status"] == "error"

    def test_dashboard_full_structure(self, tmp_path, monkeypatch):
        """Single test that checks all dashboard structure in one call.

        Consolidates: top_level_fields, tab_structure, kpis, subtabs,
        ratio_grid, percentile — was 7 separate dashboard() calls.
        """
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")

        # Top-level fields
        assert r["status"] == "ok"
        assert "tabs" in r and "kpis" in r and "company_header" in r and "freshness_footer" in r

        # Tab structure
        names = [t["name"] for t in r["tabs"]]
        assert "Overview" in names
        assert "Valuation" in names
        assert "Profitability" in names
        assert "Ratio Grid" in names
        assert "Percentile Analysis" in names
        assert "Liquidez e Alavancagem" in names
        assert "Eficiencia e Crescimento" in names
        assert "Risco de Mercado" in names
        # [v4] 8 or 9 tabs (Advanced Valuation conditional)
        assert 8 <= len(names) <= 9
        groups = [t.get("group") for t in r["tabs"]]
        assert "Resumo" in groups and "Avaliação" in groups and "Análise" in groups

        # KPIs
        assert len(r["kpis"]) == 17
        labels = [k["label"] for k in r["kpis"]]
        assert "P/L" in labels and "ROE" in labels and "Marg. Bruta" in labels
        assert "COE (CAPM)" in labels
        assert "Beta (5A)" in labels
        assert "Cresc. Receita" in labels
        assert "Cresc. Lucro" in labels

        # Valuation subtabs
        val_tab = next(t for t in r["tabs"] if t["name"] == "Valuation")
        assert val_tab["sections"][0]["type"] == "subtabs"
        sub_names = [st["name"] for st in val_tab["sections"][0]["tabs"]]
        assert "Percentil" in sub_names and "Tendência" in sub_names

        # Profitability subtabs
        prof_tab = next(t for t in r["tabs"] if t["name"] == "Profitability")
        assert prof_tab["sections"][0]["type"] == "subtabs"

        # Ratio Grid has tables
        grid_tab = next(t for t in r["tabs"] if t["name"] == "Ratio Grid")
        types = [s.get("type") for s in grid_tab["sections"]]
        assert "table" in types

        # Percentile has tables
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
    # [v6] Mock Advanced Valuation metrics so test doesn't hit real DB
    monkeypatch.setattr("skills.cvm.calculations.metrics.wacc.wacc_at", lambda c, d: None)
    monkeypatch.setattr("skills.cvm.calculations.metrics.dupont.dupont_at", lambda c, d: None)
    monkeypatch.setattr("skills.cvm.calculations.metrics.altman_z.altman_z_at", lambda c, d: None)
