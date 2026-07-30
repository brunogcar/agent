"""Tests for historical dashboard mode."""
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
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Percentile Analysis", "Trend"]

    def test_dashboard_top_level_kpis(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert len(r["kpis"]) == 6
        labels = [k["label"] for k in r["kpis"]]
        assert "P/L" in labels
        assert "ROE" in labels

    def test_dashboard_pl_kpi_present(self, tmp_path, monkeypatch):
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        kpi = next(k for k in r["kpis"] if k["label"] == "P/L")
        assert kpi is not None


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
