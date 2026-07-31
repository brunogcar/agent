"""Tests for the `dashboard` mode of skills/cvm/valuation (v1.5 6-tab reorg).

Covers TestDashboardMode (8 tests):
  - test_dashboard_no_company                : empty company -> status=error
  - test_dashboard_tab_structure             : 6 tabs with expected names + each has `sections`
  - test_dashboard_overview_kpis             : 6 KPI cards with expected labels (P/L, P/VPA, etc.)
  - test_dashboard_multiples_table           : Multiples tab carries a top-10 multiples table
  - test_dashboard_per_share_table           : Per-share tab carries a per-share values table
  - test_dashboard_profitability_ratio_grid  : Profitability tab carries a ratio_grid
  - test_dashboard_liquidity_ratio_grid      : Liquidity & Leverage tab carries a ratio_grid with 2 categories
  - test_dashboard_surfaces_ratios_data      : values from ratios() flow through to dashboard items

Uses the shared `valuation_env` fixture from conftest.py (mocks engines +
compute_all_ratios + _get_price).
"""
from __future__ import annotations


class TestDashboardMode:
    """[v1.5] Tests for `valuation.dashboard()` -- 6-tab composition mode."""

    def test_dashboard_no_company(self, valuation_env):
        """Empty company -> status=error (does NOT touch engines)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dashboard_tab_structure(self, valuation_env):
        """Returns 6 tabs with the expected names + each tab has `sections`."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 6
        expected_names = [
            "Overview",
            "Multiples",
            "Per-share",
            "Profitability",
            "Liquidity & Leverage",
            "Efficiency & Growth",
        ]
        assert [t["name"] for t in result["tabs"]] == expected_names
        # Every tab must have a `sections` list (the Overview tab also has
        # `kpis` at the top level, but `sections` is the universal key).
        for tab in result["tabs"]:
            assert "sections" in tab, f"tab {tab['name']} missing 'sections'"
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1, (
                f"tab {tab['name']} has empty sections")

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
        """Multiples tab carries a top-10 multiples table as sections[0]."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        multiples_tab = result["tabs"][1]
        assert multiples_tab["name"] == "Multiples"
        section = multiples_tab["sections"][0]
        assert section["type"] == "table"
        assert section["columns"] == ["Métrica", "Valor", "Interpretação"]
        # Top-10 multiples expected in the table.
        assert len(section["rows"]) == 10
        # First row should be P/L (label in column 0).
        assert section["rows"][0][0] == "P/L"
        # Multiples tab has at least 2 more sections: chart + collapsible.
        assert len(multiples_tab["sections"]) >= 3

    def test_dashboard_per_share_table(self, valuation_env):
        """Per-share tab carries a per-share values table as sections[0]."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        per_share_tab = result["tabs"][2]
        assert per_share_tab["name"] == "Per-share"
        section = per_share_tab["sections"][0]
        assert section["type"] == "table"
        assert section["columns"] == ["Métrica", "Valor (R$)", "Preço/Valor"]
        # All 9 per-share items expected.
        assert len(section["rows"]) == 9
        # First row should be LPA.
        assert section["rows"][0][0] == "LPA"

    def test_dashboard_profitability_ratio_grid(self, valuation_env):
        """Profitability tab carries a ratio_grid (NOT a table) as sections[0]."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        profitability_tab = result["tabs"][3]
        assert profitability_tab["name"] == "Profitability"
        section = profitability_tab["sections"][0]
        assert section["type"] == "ratio_grid"
        assert "categories" in section
        assert len(section["categories"]) == 1
        assert section["categories"][0]["label"] == "Profitability"
        # 9 profitability metrics (ROE/ROA/ROIC + 6 margins).
        assert len(section["categories"][0]["items"]) == 9

    def test_dashboard_liquidity_ratio_grid(self, valuation_env):
        """Liquidity & Leverage tab carries a ratio_grid with 2 categories."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        ll_tab = result["tabs"][4]
        assert ll_tab["name"] == "Liquidity & Leverage"
        section = ll_tab["sections"][0]
        assert section["type"] == "ratio_grid"
        assert len(section["categories"]) == 2
        labels = [c["label"] for c in section["categories"]]
        assert labels == ["Liquidity", "Leverage"]
        # Liquidity has 4 items; Leverage has 5 items.
        assert len(section["categories"][0]["items"]) == 4
        assert len(section["categories"][1]["items"]) == 5
        # Tab also has a "Detailed Leverage" collapsible section.
        collapsibles = [s for s in ll_tab["sections"] if s.get("type") == "collapsible"]
        assert len(collapsibles) == 1
        assert collapsibles[0]["title"] == "Detailed Leverage"

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

    def test_dashboard_overview_collapsible(self, valuation_env):
        """Overview tab has a Price Details collapsible section."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        overview_tab = result["tabs"][0]
        assert overview_tab["name"] == "Overview"
        collapsibles = [
            s for s in overview_tab["sections"]
            if s.get("type") == "collapsible"
        ]
        assert len(collapsibles) == 1
        assert collapsibles[0]["title"] == "Price Details"
