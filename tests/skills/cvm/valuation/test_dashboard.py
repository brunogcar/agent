"""Tests for the `dashboard` mode of skills/cvm/valuation (v1.6-valuation-split).

Covers TestDashboardMode (6 tests):
  - test_dashboard_no_company              : empty company -> status=error
  - test_dashboard_tab_structure           : 5 tabs with expected names + each has `sections`
  - test_dashboard_overview_kpis           : 6 KPI cards with expected labels (P/L, P/VPA, etc.)
  - test_dashboard_multiples_items         : Multiples tab carries 11 price-ratio items
  - test_dashboard_profitability_items     : Profitability tab carries 10 returns+margins items
  - test_dashboard_surfaces_ratios_data    : values from ratios() flow through to dashboard items

Uses the shared `valuation_env` fixture from conftest.py (mocks engines +
compute_all_ratios + _get_price).
"""
from __future__ import annotations


class TestDashboardMode:
    """[v1.6-valuation-split] Tests for `valuation.dashboard()` -- thin composition mode."""

    def test_dashboard_no_company(self, valuation_env):
        """Empty company -> status=error (does NOT touch engines)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dashboard_tab_structure(self, valuation_env):
        """Returns 5 tabs with the expected names + each tab has `sections`."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 5
        expected_names = [
            "Overview",
            "Multiples",
            "Profitability",
            "Liquidity & Leverage",
            "Efficiency & Growth",
        ]
        assert [t["name"] for t in result["tabs"]] == expected_names
        # Every tab must have a `sections` list (the Overview tab also has
        # `kpis`, but `sections` is the universal key).
        for tab in result["tabs"]:
            assert "sections" in tab, f"tab {tab['name']} missing 'sections'"
            assert isinstance(tab["sections"], list)

    def test_dashboard_overview_kpis(self, valuation_env):
        """Overview tab carries 6 KPI cards with the expected labels."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        overview = result["tabs"][0]
        assert overview["name"] == "Overview"
        assert "kpis" in overview
        assert len(overview["kpis"]) == 6
        labels = [k["label"] for k in overview["kpis"]]
        # The 6 KPI labels per the dashboard spec -- exact-match to lock the contract.
        assert labels == [
            "P/L",
            "P/VPA",
            "EV/EBITDA",
            "Dividend Yield",
            "Market Cap",
            "ROE",
        ]
        # Each KPI card has a value (may be None when DBs missing) + unit.
        for card in overview["kpis"]:
            assert "value" in card
            assert "unit" in card

    def test_dashboard_multiples_items(self, valuation_env):
        """Multiples tab carries 11 ratio items (P/L, P/VPA, P/EBIT, P/FCO,
        P/FCF, EV/EBITDA, EV/Sales, EV/FCF, PSR, Graham Number, P/Tangible Book).
        """
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        multiples_tab = result["tabs"][1]
        assert multiples_tab["name"] == "Multiples"
        ratio_grid_section = next(
            (s for s in multiples_tab["sections"] if s.get("name") == "ratio_grid"),
            None,
        )
        assert ratio_grid_section is not None, "ratio_grid section missing from Multiples tab"
        assert "items" in ratio_grid_section
        items = ratio_grid_section["items"]
        assert len(items) == 11
        labels = [it["label"] for it in items]
        # Lock the exact label contract (order matters -- dashboards render in order).
        assert labels == [
            "P/L", "P/VPA", "P/EBIT", "P/FCO", "P/FCF",
            "EV/EBITDA", "EV/Sales", "EV/FCF", "PSR",
            "Graham Number", "P/Tangible Book",
        ]
        # Each item must have a value (may be None) + unit.
        for item in items:
            assert "value" in item
            assert "unit" in item

    def test_dashboard_profitability_items(self, valuation_env):
        """Profitability tab carries 10 ratio items (ROE/ROA/ROIC + 6 margins + Effective Tax Rate)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        profitability_tab = result["tabs"][2]
        assert profitability_tab["name"] == "Profitability"
        ratio_grid_section = next(
            (s for s in profitability_tab["sections"] if s.get("name") == "ratio_grid"),
            None,
        )
        assert ratio_grid_section is not None
        items = ratio_grid_section["items"]
        assert len(items) == 10
        labels = [it["label"] for it in items]
        assert labels == [
            "ROE", "ROA", "ROIC",
            "Gross Margin", "Operating Margin", "Net Margin",
            "EBITDA Margin", "OCF Margin", "FCF Margin",
            "Effective Tax Rate",
        ]

    def test_dashboard_surfaces_ratios_data(self, valuation_env):
        """Values from ratios() are surfaced in the dashboard's Multiples tab.

        The valuation_env fixture mocks compute_all_ratios to return
        deterministic values -- verify those land in the dashboard items:
          - p_l (manual computation) = 500.5e9 / 120e9 ~ 4.17
          - ev_ebitda (registry mock) = 6.71
          - graham_number (registry mock) = 75.0
          - roe (registry mock, Overview KPI) = 0.28
        """
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"

        # Multiples tab -- p_l + ev_ebitda + graham_number all populated
        multiples_tab = result["tabs"][1]
        multiples_items = multiples_tab["sections"][0]["items"]
        multiples_by_label = {it["label"]: it for it in multiples_items}
        assert multiples_by_label["P/L"]["value"] is not None
        assert 3.5 < multiples_by_label["P/L"]["value"] < 4.5
        assert multiples_by_label["EV/EBITDA"]["value"] == 6.71
        assert multiples_by_label["Graham Number"]["value"] == 75.0

        # Overview tab -- ROE KPI populated from the registry mock
        overview = result["tabs"][0]
        roe_kpi = next(k for k in overview["kpis"] if k["label"] == "ROE")
        assert roe_kpi["value"] == 0.28
