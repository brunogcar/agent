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
        """Overview tab carries 6 KPI cards with the expected labels."""
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        overview = result["tabs"][0]
        assert overview["name"] == "Overview"
        assert "kpis" in overview
        assert len(overview["kpis"]) == 6
        labels = [k["label"] for k in overview["kpis"]]
        # The 6 KPI labels per the spec — exact-match to lock the contract.
        assert labels == [
            "Receita Líquida",
            "EBITDA",
            "Lucro Líquido",
            "Margem EBITDA",
            "ROE",
            "Dívida Líquida/EBITDA",
        ]
        # Each KPI card has a value (may be None when DBs missing) + unit.
        for card in overview["kpis"]:
            assert "value" in card
            assert "unit" in card

    def test_dashboard_ratios_grid(self, financials_env):
        """Ratios tab carries a ratio_grid grouped by metric category.

        The grid must include at least the 6 categories used by summary():
        profitability, liquidity, leverage, efficiency, growth, tax. Each
        category should contain a dict of {metric_name: value_or_None} for
        the registered metrics in that category (excluding per-share).
        """
        from skills.cvm.financials.modes.dashboard import dashboard
        result = dashboard(company="33000167000101")
        assert result["status"] == "ok"
        ratios_tab = result["tabs"][4]
        assert ratios_tab["name"] == "Ratios"
        assert "sections" in ratios_tab
        ratio_grid_section = next(
            (s for s in ratios_tab["sections"] if s.get("name") == "ratio_grid"),
            None,
        )
        assert ratio_grid_section is not None, "ratio_grid section missing"
        assert "categories" in ratio_grid_section
        categories = ratio_grid_section["categories"]
        # Each of the 6 expected categories must be present (per-share is NOT
        # in this list because the dashboard filters it out, same as summary()).
        for cat in ("profitability", "liquidity", "leverage",
                    "efficiency", "growth", "tax"):
            assert cat in categories, \
                f"ratio_grid missing category '{cat}' (got {sorted(categories.keys())})"
        # Profitability should contain at least roe/roa/roic (9 metrics total).
        prof = categories["profitability"]
        for metric_name in ("roe", "roa", "roic"):
            assert metric_name in prof, \
                f"profitability grid missing '{metric_name}' (got {sorted(prof.keys())})"
        # Per-share metrics must NOT leak into any category bucket.
        for cat, metrics in categories.items():
            for excluded in ("lpa", "vpa", "dpa", "rps"):
                assert excluded not in metrics, \
                    f"per-share '{excluded}' leaked into category '{cat}'"
