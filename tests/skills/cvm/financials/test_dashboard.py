"""Tests for the `dashboard` mode of skills/cvm/financials (v1.12).

Covers TestDashboardMode (4 tests):
  - test_dashboard_no_company         : empty company → status=error
  - test_dashboard_tab_structure      : returns 7 tabs (Overview / Indicadores /
                                        Crescimento / Balanço / DRE / DFC / DVA)
  - test_dashboard_overview_kpis      : top-level KPI cards with expected labels
  - test_dashboard_indicadores_grid   : Indicadores tab carries a ratio_grid
                                        section with all 7 ratio categories

Uses the shared `financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestDashboardMode:
    """[v1.12] Tests for `financials.dashboard()` — 7-tab composition mode."""

    def test_dashboard_no_company(self, financials_env):
        """Empty company → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dashboard_tab_structure(self, financials_env):
        """Returns 9 tabs with the expected names + each tab has `sections`."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 9
        expected_names = [
            "Overview", "Indicadores", "Crescimento",
            "Balanço", "DRE", "DFC", "DVA",
            "TTM", "YoY Quarterly",
        ]
        assert [t["name"] for t in result["tabs"]] == expected_names
        # Every tab must have a `sections` list (the Overview tab also has
        # `kpis`, but `sections` is the universal key).
        for tab in result["tabs"]:
            assert "sections" in tab, f"tab {tab['name']} missing 'sections'"
            assert isinstance(tab["sections"], list)

    def test_dashboard_overview_kpis(self, financials_env):
        """Top-level KPI cards with the expected labels (v1.12 spec)."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        assert "kpis" in result
        assert len(result["kpis"]) == 6
        labels = [k["label"] for k in result["kpis"]]
        # The 6 KPI labels per the v1.12 spec — exact-match to lock the contract.
        assert labels == [
            "Receita (TTM)",
            "EBITDA",
            "Lucro Líquido",
            "ROE",
            "ROIC",
            "Dívida Líquida/EBITDA",
        ]
        # Each KPI card has a label + value + unit.
        for card in result["kpis"]:
            assert "label" in card
            assert "value" in card

    def test_dashboard_indicadores_grid(self, financials_env):
        """Indicadores tab (index 1) uses type=subtabs (v1.13 review-fix).

        [v1.13] Previously a single ratio_grid with all 7 categories as
        cards.  Now each category is its own sub-tab, each carrying a
        single-category ratio_grid.  This verifies the subtabs structure
        + that each sub-tab has a ratio_grid with at least one category.
        """
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        indicadores_tab = result["tabs"][1]
        assert indicadores_tab["name"] == "Indicadores"
        assert "sections" in indicadores_tab
        section = indicadores_tab["sections"][0]
        # [v1.13] Now a subtabs section, not a flat ratio_grid.
        assert section["type"] == "subtabs"
        assert "tabs" in section
        assert isinstance(section["tabs"], list)
        assert len(section["tabs"]) > 0
        # Each sub-tab must carry a ratio_grid section with ≥1 category.
        for sub in section["tabs"]:
            assert "name" in sub
            assert "sections" in sub
            assert len(sub["sections"]) >= 1
            rg = sub["sections"][0]
            assert rg["type"] == "ratio_grid"
            assert isinstance(rg.get("categories"), list)
            assert len(rg["categories"]) >= 1

    def test_dashboard_balanco_uses_subtabs(self, financials_env):
        """Balanço tab uses type=subtabs with BPA + BPP sub-tabs."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        balanco_tab = next(t for t in result["tabs"] if t["name"] == "Balanço")
        assert len(balanco_tab["sections"]) == 1
        sec = balanco_tab["sections"][0]
        assert sec["type"] == "subtabs"
        sub_names = [t["name"] for t in sec["tabs"]]
        assert sub_names == ["BPA", "BPP"]

    def test_dashboard_dre_has_table_and_chart(self, financials_env):
        """DRE tab carries a table section + a chart section (margin trend)."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        dre_tab = next(t for t in result["tabs"] if t["name"] == "DRE")
        types = [s.get("type") for s in dre_tab["sections"]]
        assert "table" in types
        # The margin-trend chart is only present when 2+ annual periods exist
        # in the synthetic DB (2023 + 2022). Both are present in conftest.
        assert "chart" in types

    def test_dashboard_dfc_has_table_and_chart(self, financials_env):
        """DFC tab carries a table section + a chart section (stacked bar)."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        dfc_tab = next(t for t in result["tabs"] if t["name"] == "DFC")
        types = [s.get("type") for s in dfc_tab["sections"]]
        assert "table" in types
        assert "chart" in types
