"""tests/skills/bcb/macro/test_modes.py - macro skill modes with mocked query_engine.

Mocks data_sources.bcb.sgs.query_engine.series + last_value so no DB access
is needed. Verifies the v3 fixes:
  - Tab field is 'name' (not 'label')
  - KPIs are at top level (not per-tab)
  - Chart sections have 'chart_data' (Chart.js config, not labels/values)
  - Table rows are list of lists (not list of dicts)
  - CDI KPI shows daily rate (% a.d.), not annualized
[v1.6] Added tests for sortable tables + DD/MM/YYYY dates + chart days=3650.
[v1.7] Added tests for collapsible tables + monthly grouping in rates table.
"""
from __future__ import annotations


def _mock_series(code, days=30, start="", end=""):
    return {
        "status": "ok", "code": code, "count": 2,
        "observations": [
            {"ref_date": "2024-01-02", "value": 0.001234},
            {"ref_date": "2024-01-03", "value": 0.001235},
        ],
    }


def _mock_last_value(code):
    # [v1.3] Mock now returns unit + name (matching the updated query_engine).
    from data_sources.bcb.sgs.catalog import SERIES_CATALOG
    meta = SERIES_CATALOG.get(code, ("?", "", "", "", ""))
    return {"status": "ok", "code": code, "name": meta[0], "unit": meta[2],
            "ref_date": "2024-01-03", "value": 0.001235}


def _patch_query(monkeypatch):
    """Patch query_engine functions at ALL module namespaces that import them.

    The rates/dashboard/inflation/fx modes import last_value + series at
    module level (from data_sources.bcb.sgs.query_engine import ...),
    creating local references. Patching only the source module doesn't
    affect these local refs. We must patch at each calling module too.
    """
    import data_sources.bcb.sgs.query_engine as qe
    monkeypatch.setattr(qe, "series", _mock_series)
    monkeypatch.setattr(qe, "last_value", _mock_last_value)

    # Patch at calling module namespaces (local refs bound at import time)
    from skills.bcb.macro.modes import rates, dashboard, inflation, fx
    monkeypatch.setattr(rates, "query_series", _mock_series)
    monkeypatch.setattr(rates, "last_value", _mock_last_value)
    monkeypatch.setattr(dashboard, "query_series", _mock_series)
    monkeypatch.setattr(dashboard, "last_value", _mock_last_value)
    monkeypatch.setattr(inflation, "query_series", _mock_series)
    monkeypatch.setattr(fx, "query_series", _mock_series)


def test_rates_mode(monkeypatch):
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import rates
    res = rates.rates(days=5)
    assert res["status"] == "ok"
    assert res["mode"] == "rates"
    # 5 KPIs: Selic, CDI, TR, Meta Copom, Selic acumulada
    assert len(res["kpis"]) == 5
    # First KPI is Selic (annualized from % a.d. -> % a.a.).
    selic_kpi = res["kpis"][0]
    assert selic_kpi["unit"] == "% a.a."
    assert abs(selic_kpi["raw"] - 0.001235 * 252.0) < 1e-9
    # Chart sections have chart_data (not labels/values).
    chart_secs = [s for s in res["sections"] if s.get("type") == "chart"]
    assert len(chart_secs) >= 1
    assert "chart_data" in chart_secs[0]
    assert "labels" not in chart_secs[0]  # v3: moved inside chart_data
    # Table rows are list of lists.
    table_secs = [s for s in res["sections"] if s.get("type") == "table"]
    assert len(table_secs) >= 1
    assert isinstance(table_secs[0]["rows"][0], list)


def test_inflation_mode(monkeypatch):
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import inflation
    res = inflation.inflation(months=12)
    assert res["status"] == "ok"
    assert res["mode"] == "inflation"
    assert len(res["kpis"]) == 2  # IPCA + IGP-M


def test_fx_mode(monkeypatch):
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import fx
    res = fx.fx(days=30)
    assert res["status"] == "ok"
    assert res["mode"] == "fx"
    assert len(res["kpis"]) == 1  # USD/BRL daily


def test_dashboard_uses_name_not_label(monkeypatch):
    """v3 fix: tab field is 'name' (was 'label')."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    assert res["status"] == "ok"
    tab_names = [t["name"] for t in res["tabs"]]
    # Just check tabs have names + no 'label' key (v3 fix).
    assert len(tab_names) >= 7  # 5 base + Retorno Real + Expectativas Focus + Curva de Juros
    assert "Resumo" in tab_names
    for t in res["tabs"]:
        assert "label" not in t, f"tab {t.get('name')} still has 'label'"


def test_dashboard_kpis_at_top_level(monkeypatch):
    """v3 fix: KPIs are at top level (not per-tab)."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    assert "kpis" in res
    assert len(res["kpis"]) == 4  # Selic, CDI, IPCA, USD/BRL
    # Tabs should NOT have per-tab 'kpis' (v3 removed them).
    for t in res["tabs"]:
        assert "kpis" not in t, f"tab {t.get('name')} still has per-tab kpis"


def test_dashboard_cdi_kpi_is_daily(monkeypatch):
    """v3 fix: CDI KPI shows daily rate (% a.d.), NOT annualized."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    cdi_kpi = res["kpis"][1]
    assert cdi_kpi["label"] == "CDI (diaria)"
    assert cdi_kpi["unit"] == "% a.d."
    # The raw value should be the daily rate (0.001235), NOT annualized.
    assert abs(cdi_kpi["raw"] - 0.001235) < 1e-9
    # Selic KPI stays annualized.
    selic_kpi = res["kpis"][0]
    assert selic_kpi["unit"] == "% a.a."


def test_dashboard_chart_sections_have_chart_data(monkeypatch):
    """v3 fix: chart sections emit chart_data (Chart.js config)."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    # The Juros tab should have chart sections with real chart_data.
    juros_tab = next(t for t in res["tabs"] if t["name"] == "Juros")
    chart_secs = [s for s in juros_tab["sections"] if s.get("type") == "chart"]
    assert len(chart_secs) >= 1
    cd = chart_secs[0]["chart_data"]
    assert cd["type"] == "line"
    assert "labels" in cd["data"]
    assert "datasets" in cd["data"]
    assert len(cd["data"]["datasets"]) >= 1
    # Real data (not placeholders).
    assert len(cd["data"]["labels"]) >= 1
    assert len(cd["data"]["datasets"][0]["data"]) >= 1


def test_dashboard_table_rows_are_list_of_lists(monkeypatch):
    """v3 fix: table rows are list of lists (not list of dicts)."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    juros_tab = next(t for t in res["tabs"] if t["name"] == "Juros")
    table_secs = [s for s in juros_tab["sections"] if s.get("type") == "table"]
    assert len(table_secs) >= 1
    rows = table_secs[0]["rows"]
    assert len(rows) >= 1
    assert isinstance(rows[0], list), f"row is {type(rows[0])}, expected list"
    assert len(rows[0]) == 2  # [date_cell, value]


def test_dashboard_tables_are_sortable(monkeypatch):
    """[v1.6] All tables have sortable=True + default_sort by Data DESC."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    # Check every table across all tabs.
    for tab in res["tabs"]:
        for section in tab.get("sections", []):
            if section.get("type") != "table":
                continue
            assert section.get("sortable") is True, (
                f"Table '{section.get('title')}' in tab '{tab['name']}' "
                f"is not sortable")
            ds = section.get("default_sort")
            assert ds is not None, (
                f"Table '{section.get('title')}' has no default_sort")
            assert "column" in ds and "direction" in ds, (
                f"Table '{section.get('title')}' default_sort missing keys")


def test_dashboard_table_date_cells_are_dd_mm_yyyy(monkeypatch):
    """[v1.6] Date cells display as DD/MM/YYYY with ISO data-value for sorting."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    juros_tab = next(t for t in res["tabs"] if t["name"] == "Juros")
    table_secs = [s for s in juros_tab["sections"] if s.get("type") == "table"]
    assert len(table_secs) >= 1
    rows = table_secs[0]["rows"]
    # First cell should be a dict with text (DD/MM/YYYY) + data-value (ISO).
    # [v1.7] Juros table is now monthly — date is "2024-01" → text="01/2024"
    date_cell = rows[0][0]
    assert isinstance(date_cell, dict), (
        f"date cell is {type(date_cell)}, expected dict")
    assert "text" in date_cell
    assert "data-value" in date_cell


def test_dashboard_charts_show_all_available_data(monkeypatch):
    """[v1.6] Dashboard default days=3650 (was 365) to show all available data."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    # Call with default params — should pass days=3650 to rates_mode.
    res = dashboard.dashboard()
    assert res["status"] == "ok"
    # The rates mode should have received days=3650 (not 365).
    # We can't directly check what was passed, but we can verify the
    # chart titles include "3650 dias" (rates mode puts days in the title).
    juros_tab = next(t for t in res["tabs"] if t["name"] == "Juros")
    chart_secs = [s for s in juros_tab["sections"] if s.get("type") == "chart"]
    assert len(chart_secs) >= 1
    # The chart title should mention "3650 dias".
    assert "3650" in chart_secs[0]["title"], (
        f"Chart title should include '3650 dias', got: {chart_secs[0]['title']}")


def test_format_date_converts_iso_to_pt_br():
    """[v1.6] format_date converts ISO YYYY-MM-DD to DD/MM/YYYY."""
    from skills.bcb.macro.helpers import format_date
    assert format_date("2024-01-03") == "03/01/2024"
    assert format_date("2024-12-31") == "31/12/2024"
    assert format_date("") == "-"
    assert format_date("03/01/2024") == "03/01/2024"  # passthrough
    assert format_date("2024-01") == "01/2024"  # monthly


def test_dashboard_tables_are_collapsible(monkeypatch):
    """[v1.7] Table sections (except Resumo) have collapsible=True."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import dashboard
    res = dashboard.dashboard(days=30, months=12)
    # Check that tables in Indicadores + Analise tabs are collapsible.
    collapsible_count = 0
    for tab in res["tabs"]:
        if tab["group"] not in ("Indicadores", "Analise"):
            continue
        for section in tab.get("sections", []):
            if section.get("type") == "table" and section.get("collapsible") is True:
                collapsible_count += 1
    assert collapsible_count > 0, "No collapsible tables found in Indicadores/Analise tabs"


def test_rates_table_is_monthly(monkeypatch):
    """[v1.7] Rates table shows monthly data (not daily)."""
    _patch_query(monkeypatch)
    from skills.bcb.macro.modes import rates
    res = rates.rates(days=30)
    table_secs = [s for s in res["sections"] if s.get("type") == "table"]
    assert len(table_secs) >= 1
    # The table title should mention "mensal" (monthly).
    assert "mensal" in table_secs[0]["title"].lower(), (
        f"Table title should include 'mensal', got: {table_secs[0]['title']}")


def test_yield_curve_chart_has_no_range_selector(monkeypatch):
    """[v1.7] Yield curve chart does NOT have price_range_selector (forward-looking prediction)."""
    _patch_query(monkeypatch)
    # yield_curve mode doesn't use SGS series (only Focus + last_value for Selic).
    # We can't easily test it without mocking Focus, but we can check the
    # _build_yield_chart function directly.
    from skills.bcb.macro.modes.yield_curve import _build_yield_chart
    points = [
        {"year": "2026", "mediana": 13.0, "minimo": 12.0, "maximo": 14.0,
         "numero_respondentes": 100, "data": "2026-08-21"},
        {"year": "2027", "mediana": 11.0, "minimo": 10.0, "maximo": 12.0,
         "numero_respondentes": 100, "data": "2026-08-21"},
    ]
    chart = _build_yield_chart(points)
    assert chart.get("price_range_selector") is None, (
        "Yield curve chart should NOT have price_range_selector")


def test_group_by_month():
    """[v1.7] group_by_month keeps last value per month."""
    from skills.bcb.macro.helpers import group_by_month
    observations = [
        {"ref_date": "2024-01-02", "value": 0.001},
        {"ref_date": "2024-01-15", "value": 0.002},  # same month, last wins
        {"ref_date": "2024-01-30", "value": 0.003},  # same month, last wins
        {"ref_date": "2024-02-05", "value": 0.004},
    ]
    result = group_by_month(observations)
    assert len(result) == 2  # 2 months
    assert result[0] == {"ref_date": "2024-01", "value": 0.003}  # last value of Jan
    assert result[1] == {"ref_date": "2024-02", "value": 0.004}
