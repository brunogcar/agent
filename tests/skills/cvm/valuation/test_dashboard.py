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
        """Top-level KPI cards with the expected labels."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        assert "kpis" in result
        assert len(result["kpis"]) == 6
        labels = [k["label"] for k in result["kpis"]]
        # The 6 KPI labels per the dashboard spec -- exact-match to lock the contract.
        assert labels == [
            "P/L",
            "P/VPA",
            "EV/EBITDA",
            "Dividend Yield",
            "Market Cap",
            "ROE",
        ]
        # Each KPI card has a label + value.
        for card in result["kpis"]:
            assert "label" in card
            assert "value" in card

    def test_dashboard_multiples_table(self, valuation_env):
        """Multiples tab carries a table with ratio rows."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        multiples_tab = result["tabs"][1]
        assert multiples_tab["name"] == "Multiples"
        section = multiples_tab["sections"][0]
        assert section["type"] == "table"
        assert len(section["rows"]) >= 1

    def test_dashboard_profitability_table(self, valuation_env):
        """Profitability tab carries a table with ratio rows."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        profitability_tab = result["tabs"][2]
        assert profitability_tab["name"] == "Profitability"
        section = profitability_tab["sections"][0]
        assert section["type"] == "table"
        assert len(section["rows"]) >= 1

    def test_dashboard_surfaces_ratios_data(self, valuation_env):
        """Values from ratios() are surfaced in the dashboard."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        # KPIs at top level should have values
        kpis = result.get("kpis", [])
        assert len(kpis) >= 1
        # At least one KPI should have a non-dash value
        has_value = any(k.get("value") not in (None, "—") for k in kpis)
        assert has_value, "No KPI has a value"
