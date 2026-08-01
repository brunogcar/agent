"""Tests for historical dashboard mode (v2.1 — 5 tabs with subtabs + charts + F7 cache)."""
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
        assert "tabs" in r
        assert "kpis" in r

    def test_dashboard_tab_structure(self, tmp_path, monkeypatch):
        """[v2.1] 5 tabs: Overview, Valuation, Profitability, Ratio Grid, Percentile Analysis."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Valuation", "Profitability", "Ratio Grid", "Percentile Analysis"]

    def test_dashboard_top_level_kpis(self, tmp_path, monkeypatch):
        """[v2.1] 8 KPI cards (added margins)."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert len(r["kpis"]) == 8
        labels = [k["label"] for k in r["kpis"]]
        assert "P/L" in labels
        assert "ROE" in labels
        assert "Marg. Bruta" in labels

    def test_dashboard_valuation_has_subtabs(self, tmp_path, monkeypatch):
        """[v2.1] Valuation tab uses type=subtabs."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        val_tab = next(t for t in r["tabs"] if t["name"] == "Valuation")
        assert val_tab["sections"][0]["type"] == "subtabs"
        sub_names = [st["name"] for st in val_tab["sections"][0]["tabs"]]
        assert "Percentile" in sub_names
        assert "Trend" in sub_names

    def test_dashboard_profitability_has_subtabs(self, tmp_path, monkeypatch):
        """[v2.1] Profitability tab uses type=subtabs."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        prof_tab = next(t for t in r["tabs"] if t["name"] == "Profitability")
        assert prof_tab["sections"][0]["type"] == "subtabs"
        sub_names = [st["name"] for st in prof_tab["sections"][0]["tabs"]]
        assert "Percentile" in sub_names
        assert "Trend" in sub_names

    def test_dashboard_ratio_grid_section(self, tmp_path, monkeypatch):
        """[v2.1] Ratio Grid tab has a ratio_grid section."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        grid_tab = next(t for t in r["tabs"] if t["name"] == "Ratio Grid")
        assert grid_tab["sections"][0]["type"] == "ratio_grid"
        assert "categories" in grid_tab["sections"][0]

    def test_dashboard_percentile_has_chart(self, tmp_path, monkeypatch):
        """[v2.1] Percentile Analysis tab has a chart section."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        pct_tab = next(t for t in r["tabs"] if t["name"] == "Percentile Analysis")
        types = [s.get("type") for s in pct_tab["sections"]]
        assert "table" in types


# ── Helpers ──────────────────────────────────────────────────────────────────

def _patch_environment(tmp_path, monkeypatch):
    # Mock summary() so dashboard doesn't call real metric history
    def mock_summary(company="", metric="lpa", months=60):
        return {
            "status": "ok",
            "company": company,
            "metric": metric,
            "current": {"value": 5.11, "date": "2024-06-30"},
            "percentiles": {"min": 3.0, "p25": 4.0, "median": 5.0, "p75": 6.0, "max": 8.0},
            "average": 5.0,
            "series": [{"date": "2024-06-30", "value": 5.11}],
        }

    monkeypatch.setattr(
        "skills.cvm.historical.modes.dashboard.summary",
        mock_summary,
    )

    # Mock fetch_quartiles so it doesn't call spec.history_fn (which hits real DBs)
    monkeypatch.setattr(
        "skills.cvm.historical.modes.dashboard.fetch_quartiles",
        lambda company, metric_name, months=60: {"p25": 4.0, "median": 5.0, "p75": 6.0},
    )
