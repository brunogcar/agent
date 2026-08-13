"""Tests for the `dashboard` mode of skills/cvm/valuation.

[v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call is expensive (orchestrates ratios + DCF + WACC +
IRR + annual); the valuation_env fixture mocks all those slow paths, so we
call dashboard() exactly once per file to verify tab structure.

Uses the shared `valuation_env` fixture from conftest.py.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_historical_valuation(monkeypatch):
    """Mock historical_valuation for all dashboard tests."""
    import skills.cvm.valuation.modes.historical_valuation as hv_mod
    monkeypatch.setattr(hv_mod, "historical_valuation",
                        lambda company, years=5: {"status": "ok", "series": [], "metrics": []})


class TestDashboardMode:
    def test_dashboard_no_company(self, valuation_env):
        """Empty company -> status=error."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dashboard_tab_structure(self, valuation_env):
        """Dashboard returns 6 tabs with the expected names."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        assert "tabs" in result
        names = [t["name"] for t in result["tabs"]]
        assert names == [
            "Overview", "Múltiplos", "Valor Intrínseco",
            "Rentabilidade", "Liquidez e Alavancagem",
            "Eficiência e Crescimento",
        ]
        # Each tab has a sections list.
        for tab in result["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
