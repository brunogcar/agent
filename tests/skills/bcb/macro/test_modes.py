"""tests/skills/bcb/macro/test_modes.py - macro skill modes with mocked query_engine.

Mocks data_sources.bcb.sgs.query_engine.series + last_value so no DB access
is needed. Verifies the v3 fixes:
  - Tab field is 'name' (not 'label')
  - KPIs are at top level (not per-tab)
  - Chart sections have 'chart_data' (Chart.js config, not labels/values)
  - Table rows are list of lists (not list of dicts)
  - CDI KPI shows daily rate (% a.d.), not annualized
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
    assert len(rows[0]) == 2  # [date, value]
