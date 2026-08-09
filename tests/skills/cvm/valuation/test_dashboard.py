"""Tests for the `dashboard` mode of skills/cvm/valuation.

[v2.1] Removed test_dashboard_full_structure (was 116s+ on real DB).
Only kept test_dashboard_no_company (fast error path, no DB).
The dashboard structure is verified by the HTML output when running
gen_val_dashboard.py — not by unit tests.
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
