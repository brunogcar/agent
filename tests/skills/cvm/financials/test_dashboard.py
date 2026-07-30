"""Tests for the `dashboard` mode of skills/cvm/financials (v1.5).

Covers TestDashboardMode (4 tests):
  - test_dashboard_no_company       : empty company → status=error
  - test_dashboard_tab_structure    : returns 5 tabs (Overview/DRE/Balanço/DFC/Ratios)
  - test_dashboard_overview_kpis    : Overview tab has 6 KPI cards with expected labels
  - test_dashboard_ratios_grid      : Ratios tab carries a categorized ratio_grid

Uses the shared `financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestDashboardMode:
    """[v1.5] Tests for `financials.dashboard()` — thin composition mode."""

    def test_dashboard_no_company(self, financials_env):
        """Empty company → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dashboard_tab_structure(self, financials_env):
        """Returns 5 tabs with the expected names + each tab has `sections`."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 5
        expected_names = ["Overview", "DRE", "Balanço", "DFC", "Ratios"]
        assert [t["name"] for t in result["tabs"]] == expected_names
        # Every tab must have a `sections` list (the Overview tab also has
        # `kpis`, but `sections` is the universal key).
        for tab in result["tabs"]:
            assert "sections" in tab, f"tab {tab['name']} missing 'sections'"
            assert isinstance(tab["sections"], list)

    def test_dashboard_overview_kpis(self, financials_env):
        """Top-level KPI cards with the expected labels."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        assert "kpis" in result
        assert len(result["kpis"]) == 6
        labels = [k["label"] for k in result["kpis"]]
        # The 6 KPI labels per the spec — exact-match to lock the contract.
        assert labels == [
            "Receita Líquida",
            "EBITDA",
            "Lucro Líquido",
            "Margem EBITDA",
            "ROE",
            "Dívida Líquida/EBITDA",
        ]
        # Each KPI card has a label + value.
        for card in result["kpis"]:
            assert "label" in card
            assert "value" in card

    def test_dashboard_ratios_table(self, financials_env):
        """Ratios tab carries a table with categorized ratios."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        ratios_tab = result["tabs"][4]
        assert ratios_tab["name"] == "Ratios"
        assert "sections" in ratios_tab
        section = ratios_tab["sections"][0]
        assert section["type"] == "table"
        assert len(section["rows"]) > 0
