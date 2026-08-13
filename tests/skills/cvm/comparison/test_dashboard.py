"""Tests for skills/cvm/comparison/ — dashboard mode.

[v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call is expensive (orchestrates side_by_side + growth);
we call it exactly once per file.

The `_patch_underlying` helper wraps `mock_skills` (3 underlying skills)
+ patches `financials.quarterly` to return the SUZB3 quarterly fixture
so growth() has data to compute QoQ/YoY.
"""
from __future__ import annotations

from skills.cvm.comparison.modes.dashboard import dashboard
from tests.skills.cvm.comparison.conftest import (
    VAL_PETR4, VAL_VALE3, FIN_PETR4, FIN_VALE3, DIV_PETR4, DIV_VALE3,
    FIN_QUARTERLY_SUZB3,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _patch_underlying(mock_skills, monkeypatch):
    """Mock the 3 underlying skills (val/fin/div) + financials.quarterly.

    Standard happy-path setup for dashboard tests: both tickers (PETR4 +
    VALE3) have synthetic VAL/FIN/DIV data, and financials.quarterly
    returns the SUZB3 quarterly fixture so growth() can compute QoQ/YoY
    + populate the Growth tab's columns.

    The mock_skills fixture already mocks financials.quarterly with an
    empty periods list — we override it here with the populated fixture.
    """
    mock_skills(monkeypatch,
                {"PETR4": VAL_PETR4, "VALE3": VAL_VALE3},
                {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
    def fake_quarterly(company="", periods=8, consolidado=1):
        return FIN_QUARTERLY_SUZB3
    monkeypatch.setattr("skills.cvm.financials.modes.quarterly.quarterly", fake_quarterly)


class TestDashboardMode:
    def test_dashboard_requires_tickers(self):
        """No tickers -> validation error propagated from side_by_side()."""
        r = dashboard()
        assert r["status"] == "error"
        assert "tickers" in r["error"]

    def test_dashboard_tab_structure(self, mock_skills, monkeypatch):
        """[v1.2] Dashboard produces 6 tabs (added Ratio Grid)."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["PETR4", "VALE3"]
        assert "tabs" in r
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Valuation", "Financials", "Dividends",
                         "Growth", "Ratio Grid"]
        # Each tab has a non-empty sections list.
        for tab in r["tabs"]:
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1
