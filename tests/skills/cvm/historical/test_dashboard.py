"""Tests for historical dashboard mode.

[v5→v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call takes ~0.4s with mocks; we call it exactly once.
"""
from __future__ import annotations
import pytest
from skills.cvm.historical.modes.dashboard import dashboard


class TestDashboardMode:
    def test_dashboard_no_company(self):
        """Empty company → error."""
        r = dashboard()
        assert r["status"] == "error"

    def test_dashboard_tab_structure(self, tmp_path, monkeypatch):
        """Dashboard returns the expected tabs (count + names)."""
        _patch_environment(tmp_path, monkeypatch)
        r = dashboard(company="33000167000101")
        assert r["status"] == "ok"
        assert "tabs" in r
        names = [t["name"] for t in r["tabs"]]
        # [v4] 8 or 9 tabs (Advanced Valuation conditional)
        assert 8 <= len(names) <= 9
        for expected in ("Overview", "Valuation", "Profitability", "Ratio Grid",
                         "Percentile Analysis", "Liquidez e Alavancagem",
                         "Eficiencia e Crescimento", "Risco de Mercado"):
            assert expected in names


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
