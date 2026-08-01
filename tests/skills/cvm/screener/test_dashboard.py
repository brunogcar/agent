"""Tests for skills/cvm/screener/ — dashboard mode.

[Phase 4] Split out of the original single-file `test_screener.py`.
Covers the dashboard mode (multi-tab composition that orchestrates the
underlying compare() + sector() modes):

  - no company -> short-circuit error
  - basic shape (status, tabs, kpis lists)
  - tab names exactly ['Overview', 'Peers', 'Comparison']
  - top-level KPI cards (Median P/L, Median P/VPA, Median EV/EBITDA,
    Median ROE, Median Div Yield)
  - degradation when compare() returns not_found (Peers + Comparison
    tabs render empty; KPIs render '—')
  - route dispatches to dashboard mode

The mock VAL_* data + `mock_all` fixture come from the screener conftest.
"""
from __future__ import annotations

from skills.cvm.screener import MANIFEST, route
from skills.cvm.screener.modes.dashboard import dashboard
from tests.skills.cvm.screener.conftest import (
    CAD_COMPANIES, BRIDGE_SUZB3, BRIDGE_KLBN11, VAL_SUZB3, VAL_KLBN11,
)


class TestDashboardMode:
    def test_dashboard_no_company(self):
        """Empty company -> status=error with 'company is required'.

        The dashboard short-circuits before any underlying skill is called.
        """
        r = dashboard()
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dashboard_basic_shape(self, mock_all, monkeypatch):
        """Dashboard returns status=ok with top-level tabs + kpis lists."""
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        # [v2] financials.annual + FCA are now mocked in conftest._mock_all.
        r = dashboard(company="SUZB3")
        assert r["status"] == "ok"
        assert "tabs" in r
        assert "kpis" in r
        assert isinstance(r["tabs"], list)
        assert isinstance(r["kpis"], list)

    def test_dashboard_tab_names(self, mock_all, monkeypatch):
        """Tabs are exactly ['Overview', 'Peers', 'Comparison']."""
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = dashboard(company="SUZB3")
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Peers", "Comparison"]
        # Each tab has a non-empty sections list.
        for t in r["tabs"]:
            assert isinstance(t["sections"], list)
            assert len(t["sections"]) >= 1

    def test_dashboard_top_level_kpis(self, mock_all, monkeypatch):
        """5 KPI cards at the top level with exact labels + unit fields."""
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = dashboard(company="SUZB3")
        assert len(r["kpis"]) == 5
        labels = [k["label"] for k in r["kpis"]]
        assert labels == ["Median P/L", "Median P/VPA", "Median EV/EBITDA",
                          "Median ROE", "Median Div Yield"]
        # Each KPI has label + value + unit.
        for k in r["kpis"]:
            assert "label" in k
            assert "value" in k
            assert "unit" in k

    def test_dashboard_degrades_when_compare_fails(self, mock_all, monkeypatch):
        """[v4] When compare() returns an error (e.g. ticker not in bridge),
        the dashboard still renders status=ok with the full 3-tab structure
        (Overview/Peers/Comparison) + 5 KPI cards (all "—") so the HTML
        renders with the dashboard layout. The Overview tab shows the error
        message so the user knows WHY KPIs are "—"."""
        # mock_all with empty bridge_map -> bridge_lookup returns not_found
        # for the input ticker, so compare() returns status=not_found.
        mock_all(monkeypatch, CAD_COMPANIES, {}, {})
        r = dashboard(company="UNKNOWN4")
        # [v4] Dashboard renders status=ok with full structure + error message.
        assert r["status"] == "ok"
        assert "error" in r  # error message preserved in payload
        assert len(r["tabs"]) == 3  # full structure: Overview + Peers + Comparison
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Peers", "Comparison"]
        # 5 KPI cards (all "—" since no data).
        assert len(r["kpis"]) == 5
        for kpi in r["kpis"]:
            assert kpi["value"] == "—"
        # Overview tab has the error message in its text.
        overview = r["tabs"][0]
        text = overview["sections"][0].get("text", "")
        assert "Error:" in text or "not_found" in text

    def test_route_dispatches_dashboard_mode(self):
        """route(mode='dashboard') with no company returns status=error
        with 'company is required' (short-circuits in dashboard())."""
        assert "dashboard" in MANIFEST["modes"]
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dashboard_peers_tab_has_chart(self, mock_all, monkeypatch):
        """[v1.2] Peers tab has a chart section (build_top_companies_chart)."""
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = dashboard(company="SUZB3")
        peers_tab = next(t for t in r["tabs"] if t["name"] == "Peers")
        types = [s.get("type") for s in peers_tab["sections"]]
        assert "chart" in types
        # The chart section has a chart_data block with Chart.js config.
        chart = next(s for s in peers_tab["sections"] if s.get("type") == "chart")
        assert "chart_data" in chart
        assert chart["chart_data"]["type"] == "bar"
