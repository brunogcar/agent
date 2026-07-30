"""Tests for skills/cvm/comparison/modes/dashboard.py -- dashboard mode.

Covers the new dashboard mode that composes side_by_side + growth into a
multi-tab dashboard payload:
  - 5 tabs (Overview / Valuation / Financials / Dividends / Growth)
  - 4 top-level KPI cards (Cheapest P/L, Best ROE, Best Div Yield,
    Cheapest EV/EBITDA) computed across all compared tickers
  - Defensive error propagation when side_by_side() fails

The synthetic skill results (VAL_*, FIN_*, DIV_*, FIN_QUARTERLY_SUZB3) live
in conftest.py.
"""
from __future__ import annotations

import pytest

from skills.cvm.comparison.modes.dashboard import dashboard
from tests.skills.cvm.comparison.conftest import (
    VAL_PETR4, VAL_VALE3, FIN_PETR4, FIN_VALE3, DIV_PETR4, DIV_VALE3,
    FIN_QUARTERLY_SUZB3,
)


def _patch_underlying(mock_skills, monkeypatch):
    """Mock the 3 underlying skills + financials.quarterly used by growth."""
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

    def test_dashboard_requires_min_two(self):
        r = dashboard(tickers=["PETR4"])
        assert r["status"] == "error"
        assert "2 tickers" in r["error"]

    def test_dashboard_tab_structure(self, mock_skills, monkeypatch):
        """Dashboard produces 5 tabs with the canonical names."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        assert r["tickers"] == ["PETR4", "VALE3"]
        assert "tabs" in r
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Valuation", "Financials", "Dividends", "Growth"]
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

    def test_dashboard_kpi_values_preformatted(self, mock_skills, monkeypatch):
        """KPI values are pre-formatted strings of the form '<ticker> (<fmt>')."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        # PETR4 P/L = 8.2, VALE3 P/L = 6.5 → cheapest = VALE3 (6,50 in pt-BR)
        cheapest_pl = next(k for k in r["kpis"] if k["label"] == "Cheapest P/L")
        assert cheapest_pl["value"].startswith("VALE3")
        assert "6,50" in cheapest_pl["value"]
        assert cheapest_pl["unit"] == "num"

        # PETR4 ROE = 0.15, VALE3 ROE = 0.14 → best = PETR4 (15,00% in pt-BR)
        best_roe = next(k for k in r["kpis"] if k["label"] == "Best ROE")
        assert best_roe["value"].startswith("PETR4")
        assert best_roe["unit"] == "pct"

        # PETR4 DY = 0.12, VALE3 DY = 0.09 → best = PETR4
        best_dy = next(k for k in r["kpis"] if k["label"] == "Best Div Yield")
        assert best_dy["value"].startswith("PETR4")
        assert best_dy["unit"] == "pct"

        # PETR4 EV/EBITDA = 4.5, VALE3 EV/EBITDA = 3.8 → cheapest = VALE3
        cheapest_evebitda = next(k for k in r["kpis"] if k["label"] == "Cheapest EV/EBITDA")
        assert cheapest_evebitda["value"].startswith("VALE3")
        assert "3,80" in cheapest_evebitda["value"]

    def test_dashboard_overview_has_tickers_section(self, mock_skills, monkeypatch):
        """Overview tab starts with a Compared Tickers table (Ticker + Setor)."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        overview = next(t for t in r["tabs"] if t["name"] == "Overview")
        tickers_sec = overview["sections"][0]
        assert tickers_sec["title"] == "Compared Tickers"
        assert tickers_sec["type"] == "table"
        assert tickers_sec["columns"] == ["Ticker", "Setor"]
        assert [row[0] for row in tickers_sec["rows"]] == ["PETR4", "VALE3"]

    def test_dashboard_valuation_tab_is_side_by_side(self, mock_skills, monkeypatch):
        """Valuation tab has the side-by-side valuation table with P/L column."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        valuation_tab = next(t for t in r["tabs"] if t["name"] == "Valuation")
        sec = valuation_tab["sections"][0]
        assert sec["type"] == "table"
        assert sec["columns"][0] == "Ticker"
        assert "P/L" in sec["columns"]
        assert "EV/EBITDA" in sec["columns"]
        assert len(sec["rows"]) == 2

    def test_dashboard_financials_tab_is_side_by_side(self, mock_skills, monkeypatch):
        """Financials tab has the side-by-side financials table."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        financials_tab = next(t for t in r["tabs"] if t["name"] == "Financials")
        sec = financials_tab["sections"][0]
        assert sec["type"] == "table"
        assert "Receita Líquida" in sec["columns"]
        assert "ROE" in sec["columns"]

    def test_dashboard_dividends_tab_is_side_by_side(self, mock_skills, monkeypatch):
        """Dividends tab has the side-by-side dividends table."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        dividends_tab = next(t for t in r["tabs"] if t["name"] == "Dividends")
        sec = dividends_tab["sections"][0]
        assert sec["type"] == "table"
        assert "Eventos (B3)" in sec["columns"]

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

    def test_dashboard_top_level_fields(self, mock_skills, monkeypatch):
        """Top-level payload has status + tickers + tabs (list) + kpis (list)."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        assert r["status"] == "ok"
        assert isinstance(r["tickers"], list)
        assert r["tickers"] == ["PETR4", "VALE3"]
        assert isinstance(r["tabs"], list)
        assert isinstance(r["kpis"], list)

    def test_dashboard_no_errors_section_when_no_errors(self, mock_skills, monkeypatch):
        """When all tickers succeed, Overview tab has only the Compared
        Tickers section (no Per-Ticker Errors section)."""
        _patch_underlying(mock_skills, monkeypatch)
        r = dashboard(tickers=["PETR4", "VALE3"])
        overview = next(t for t in r["tabs"] if t["name"] == "Overview")
        titles = [s["title"] for s in overview["sections"]]
        assert "Compared Tickers" in titles
        assert "Per-Ticker Errors (best-effort)" not in titles
