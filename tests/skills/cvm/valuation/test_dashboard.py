"""Tests for the `dashboard` mode of skills/cvm/valuation (v1.8 5-tab reorg).

Covers TestDashboardMode (8 tests):
  - test_dashboard_no_company                : empty company -> status=error
  - test_dashboard_tab_structure             : 5 tabs with expected names + groups
  - test_dashboard_overview_kpis             : 6 KPI cards with expected labels (P/L, P/VPA, etc.)
  - test_dashboard_multiples_table           : Multiples tab carries a top-10 multiples table
  - test_dashboard_per_share_in_multiples    : Per-share table merged into Multiples tab
  - test_dashboard_profitability_ratio_grid  : Profitability tab carries a ratio_grid
  - test_dashboard_liquidity_ratio_grid      : Liquidity & Leverage tab carries a ratio_grid with 2 categories
  - test_dashboard_surfaces_ratios_data      : values from ratios() flow through to dashboard items

[v1.8] Updated for 5-tab structure (was 6): Per-share merged into Multiples,
sidebar groups added (Resumo / Fundamentos / Crescimento), profitability
builder now returns list (ratio_grid + bar chart).

Uses the shared `valuation_env` fixture from conftest.py (mocks engines +
compute_all_ratios + _get_price).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_historical_valuation(monkeypatch):
    """[v1.1] Mock historical_valuation for all dashboard tests.

    The dashboard's Histórico tab calls historical_valuation(), which runs
    9 metrics x 5 years x 4 quarters of DB queries against ITR. With the
    valuation_env fixture's mocked engines, this is fast — but the real
    ITR DB (15M rows after full sync) makes each query take seconds,
    causing tests to hang for minutes.

    These tests validate dashboard tab structure/KPIs/sections, NOT
    historical_valuation logic (which has its own tests in
    test_historical_valuation.py). Mocking here keeps all dashboard
    tests fast (<1s each) regardless of DB state.
    """
    def _mock(company, years=5):
        return {"status": "ok", "series": [], "metrics": []}

    # Patch at the source module — dashboard.py does a local import
    # (from ...historical_valuation import historical_valuation) inside
    # the function, so patching the source module ensures the mock is
    # picked up on each call.
    import skills.cvm.valuation.modes.historical_valuation as hv_mod
    monkeypatch.setattr(hv_mod, "historical_valuation", _mock)


class TestDashboardMode:
    """[v1.8] Tests for `valuation.dashboard()` -- 5-tab composition with sidebar groups."""

    def test_dashboard_no_company(self, valuation_env):
        """Empty company -> status=error (does NOT touch engines)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dashboard_tab_structure(self, valuation_env):
        """Returns 5 tabs with expected names + sidebar groups."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 6
        expected_names = [
            "Overview",
            "Múltiplos",
            "Rentabilidade",
            "Liquidez e Alavancagem",
            "Eficiência e Crescimento",
            "Histórico",
        ]
        assert [t["name"] for t in result["tabs"]] == expected_names
        # [v1.8] Every tab must have a `group` field for sidebar grouping.
        expected_groups = [
            "Resumo",
            "Resumo",
            "Fundamentos",
            "Fundamentos",
            "Crescimento",
            "Séries Temporais",
        ]
        assert [t.get("group") for t in result["tabs"]] == expected_groups
        # Every tab must have a `sections` list.
        # Note: "Histórico" tab may have empty sections in test env (no DFP DB
        # for historical_valuation mode) — that's OK, it degrades gracefully.
        for tab in result["tabs"]:
            assert "sections" in tab, f"tab {tab['name']} missing 'sections'"
            assert isinstance(tab["sections"], list)
            if tab["name"] != "Histórico":
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
        """[v1.9] Multiples tab carries split tables (Price + EV + Less Common)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        multiples_tab = result["tabs"][1]
        assert multiples_tab["name"] == "Múltiplos"
        # [v1.9] First section is now "Múltiplos de Preço" (was "Top Price Multiples").
        section = multiples_tab["sections"][0]
        assert section["type"] == "table"
        assert section["columns"] == ["Métrica", "Valor", "Interpretação"]
        # 7 price multiples (was 10 in the old combined table).
        assert len(section["rows"]) == 7
        # First row should be P/L (first cell is a dict with text + tooltip).
        first_cell = section["rows"][0][0]
        assert (first_cell["text"] if isinstance(first_cell, dict) else first_cell) == "P/L"
        # Multiples tab has: Price table + Price chart + EV table + EV chart + Less Common table + per-share sections.
        assert len(multiples_tab["sections"]) >= 5

    def test_dashboard_per_share_in_multiples(self, valuation_env):
        """[v1.8] Per-share table is merged into the Multiples tab (was a separate tab)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        multiples_tab = result["tabs"][1]
        # Find the per-share table within the Multiples tab sections.
        per_share_tables = [
            s for s in multiples_tab["sections"]
            if s.get("type") == "table"
            and s.get("columns") == ["Métrica", "Valor (R$)", "Preço/Valor"]
        ]
        assert len(per_share_tables) >= 1, "Per-share table not found in Multiples tab"
        # All 9 per-share items expected.
        assert len(per_share_tables[0]["rows"]) == 9
        # First row should be LPA.
        first_ps_cell = per_share_tables[0]["rows"][0][0]
        assert (first_ps_cell["text"] if isinstance(first_ps_cell, dict) else first_ps_cell) == "LPA"

    def test_dashboard_profitability_ratio_grid(self, valuation_env):
        """[v1.9] Profitability tab carries a ratio_grid with 2 categories (Retornos + Margens)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        profitability_tab = result["tabs"][2]
        assert profitability_tab["name"] == "Rentabilidade"
        section = profitability_tab["sections"][0]
        assert section["type"] == "ratio_grid"
        assert "categories" in section
        # [v1.9] Now 2 categories: Retornos (3 items) + Margens (6 items).
        assert len(section["categories"]) == 2
        assert section["categories"][0]["label"] == "Retornos"
        assert section["categories"][1]["label"] == "Margens"
        assert len(section["categories"][0]["items"]) == 3
        assert len(section["categories"][1]["items"]) == 6
        # Items have tooltips + value_raw.
        first_item = section["categories"][0]["items"][0]
        assert "tooltip" in first_item
        assert "value_raw" in first_item

    def test_dashboard_liquidity_ratio_grid(self, valuation_env):
        """[v1.8] Liquidity & Leverage tab (now tab index 3) carries a ratio_grid with 2 categories."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        ll_tab = result["tabs"][3]
        assert ll_tab["name"] == "Liquidez e Alavancagem"
        section = ll_tab["sections"][0]
        assert section["type"] == "ratio_grid"
        assert len(section["categories"]) == 2
        labels = [c["label"] for c in section["categories"]]
        assert labels == ["Liquidity", "Leverage"]
        # Liquidity has 4 items; Leverage has 5 items.
        assert len(section["categories"][0]["items"]) == 4
        assert len(section["categories"][1]["items"]) == 5
        # Items have tooltips.
        first_item = section["categories"][0]["items"][0]
        assert "tooltip" in first_item
        # [v1.9] Detailed Leverage is now a table (was collapsible).
        detail_tables = [
            s for s in ll_tab["sections"]
            if s.get("type") == "table" and s.get("title") == "Alavancagem Detalhada"
        ]
        assert len(detail_tables) == 1

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

    def test_dashboard_overview_tables(self, valuation_env):
        """[v1.9] Overview tab has 3 split tables (was 1 table + collapsible)."""
        from skills.cvm.valuation.modes.dashboard import dashboard
        result = dashboard(company="PETR4")
        assert result["status"] == "ok"
        overview_tab = result["tabs"][0]
        assert overview_tab["name"] == "Overview"
        # [v1.9] No more collapsibles — price info is in company_header.
        collapsibles = [s for s in overview_tab["sections"] if s.get("type") == "collapsible"]
        assert len(collapsibles) == 0
        # Should have 3 table sections: Métricas de Mercado, Resultado, Balanço.
        tables = [s for s in overview_tab["sections"] if s.get("type") == "table"]
        assert len(tables) >= 3
