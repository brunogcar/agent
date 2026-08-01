"""Tests for skills/cvm/comparison/ — dashboard mode.

[Phase 4] Split out of the original single-file `test_comparison.py`.
Covers the dashboard mode (multi-tab composition that orchestrates the
underlying side_by_side + growth modes):

  - no tickers -> validation error from side_by_side
  - tab structure (5 tabs: Overview, Valuation, Financials, Dividends, Growth)
  - top-level KPI cards (Cheapest P/L, Best ROE, Best Div Yield,
    Cheapest EV/EBITDA)
  - Growth tab has QoQ + YoY columns from growth()
  - best-effort when side_by_side captures per-ticker errors (Overview
    tab includes a 'Per-Ticker Errors' section)

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

    def test_dashboard_top_level_kpis(self, mock_skills, monkeypatch):
        """4 KPI cards at the top level with exact labels + units."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        assert "kpis" in r
        assert len(r["kpis"]) == 4
        labels = [k["label"] for k in r["kpis"]]
        assert labels == [
            "Cheapest P/L", "Best ROE", "Best Div Yield", "Cheapest EV/EBITDA",
        ]
        # Each KPI has label + value + unit.
        for kpi in r["kpis"]:
            assert "label" in kpi
            assert "value" in kpi
            assert "unit" in kpi

    def test_dashboard_growth_tab_has_qoq_yoy(self, mock_skills, monkeypatch):
        """Growth tab has QoQ + YoY columns from the growth() result."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        growth_tab = next(t for t in r["tabs"] if t["name"] == "Growth")
        sec = growth_tab["sections"][0]
        assert sec["type"] == "table"
        assert "Receita QoQ" in sec["columns"]
        assert "Receita YoY" in sec["columns"]

    def test_dashboard_propagates_side_by_side_failure(self, mock_skills, monkeypatch):
        """When side_by_side() fails (one ticker fails all 3 skills), the
        dashboard still returns status=ok (best-effort) — only validation
        errors propagate."""
        # All 3 skills error for both tickers -> side_by_side returns ok with
        # errors list; dashboard still builds tabs.
        mock_skills(monkeypatch,
                    {"PETR4": {"status": "error", "error": "no data"},
                     "VALE3": {"status": "error", "error": "no data"}},
                    {"PETR4": {"status": "error", "error": "no data"},
                     "VALE3": {"status": "error", "error": "no data"}},
                    {"PETR4": {"status": "error", "error": "no data"},
                     "VALE3": {"status": "error", "error": "no data"}})
        r = dashboard(tickers=["PETR4", "VALE3"])
        # side_by_side() returns status=ok with errors; dashboard propagates
        # that and still builds tabs.
        assert r["status"] == "ok"
        assert len(r["tabs"]) == 5
        # KPI cards fall back to "—" since all values are None.
        for kpi in r["kpis"]:
            assert kpi["value"] == "—"

    def test_dashboard_overview_includes_errors_section_when_errors(self, mock_skills, monkeypatch):
        """When side_by_side captures per-ticker errors, Overview tab includes
        a 'Per-Ticker Errors' section."""
        # VALE3 valuation fails; PETR4 succeeds -> side_by_side returns ok
        # with VALE3's valuation error in the errors list.
        mock_skills(monkeypatch,
                    {"PETR4": VAL_PETR4,
                     "VALE3": {"status": "error", "error": "no price"}},
                    {"PETR4": FIN_PETR4, "VALE3": FIN_VALE3},
                    {"PETR4": DIV_PETR4, "VALE3": DIV_VALE3})
        def fake_quarterly(company="", periods=8, consolidado=1):
            return FIN_QUARTERLY_SUZB3
        monkeypatch.setattr("skills.cvm.financials.modes.quarterly.quarterly", fake_quarterly)

        r = dashboard(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        overview = next(t for t in r["tabs"] if t["name"] == "Overview")
        titles = [s["title"] for s in overview["sections"]]
        assert "Compared Tickers" in titles
        assert "Per-Ticker Errors (best-effort)" in titles

    def test_dashboard_valuation_tab_has_chart(self, mock_skills, monkeypatch):
        """[v1.2] Valuation tab has a chart section (build_peer_comparison_chart)."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        val_tab = next(t for t in r["tabs"] if t["name"] == "Valuation")
        types = [s.get("type") for s in val_tab["sections"]]
        assert "chart" in types
        # The chart section has a chart_data block with Chart.js config.
        chart = next(s for s in val_tab["sections"] if s.get("type") == "chart")
        assert "chart_data" in chart
        assert chart["chart_data"]["type"] == "bar"
