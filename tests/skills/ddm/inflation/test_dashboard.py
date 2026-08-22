"""tests/skills/ddm/inflation/test_dashboard.py - dashboard tests with mocked query_engine.

Mocks data_sources.ddm.inflation.query_engine.index_history + last_value +
monthly_matrix so no DB / HTTP access is needed. Verifies:
  - 4 tabs total: IGP-M, IPCA, INPC, Comparativo
  - Tab field is "name" (not "label")
  - KPIs are at top level (not per-tab)
  - Per-index tabs have KPIs (3 each) + chart + table + matrix
  - Comparativo tab has NO tables (chart only)
  - Chart sections emit Chart.js config in `chart_data`
"""
from __future__ import annotations


_MOCK_HISTORY = [
    {"ref_date": "2026-07", "month_value": -1.16,
     "year_acumulado": 0.94, "acumulado_12m": 5.88},
    {"ref_date": "2026-06", "month_value": 0.18,
     "year_acumulado": 2.13, "acumulado_12m": 7.03},
    {"ref_date": "2026-05", "month_value": -0.12,
     "year_acumulado": 1.94, "acumulado_12m": 8.21},
]


_MOCK_LAST_VALUE = {
    "status": "ok", "slug": "", "name": "", "unit": "%",
    "ref_date": "2026-07", "month_value": -1.16,
    "year_acumulado": 0.94, "acumulado_12m": 5.88,
}


_MOCK_MATRIX = {
    "status": "ok", "slug": "", "name": "", "unit": "%",
    "years": [2026, 2025],
    "months": ["Ano", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez", "Ano"],
    "matrix": {
        2026: {"Jan": 0.41, "Fev": 0.78, "Mar": 0.55, "Abr": 0.32,
               "Mai": -0.12, "Jun": 0.18, "Jul": -1.16,
               "Ago": None, "Set": None, "Out": None,
               "Nov": None, "Dez": None, "Ano": 0.94},
        2025: {"Jan": 0.42, "Fev": 0.80, "Mar": 0.56, "Abr": 0.30,
               "Mai": 0.05, "Jun": 0.22, "Jul": -0.99, "Ago": 0.10,
               "Set": 0.45, "Out": 0.33, "Nov": 0.48, "Dez": 0.62,
               "Ano": 4.36},
    },
}


def _mock_index_history(slug="", limit=60):
    from data_sources.ddm.inflation.catalog import INDEX_CATALOG
    meta = INDEX_CATALOG.get(slug, (slug.upper(), "", "", "%"))
    return {
        "status": "ok", "slug": slug, "name": meta[0], "unit": "%",
        "count": len(_MOCK_HISTORY), "observations": list(_MOCK_HISTORY),
    }


def _mock_last_value(slug=""):
    from data_sources.ddm.inflation.catalog import INDEX_CATALOG
    meta = INDEX_CATALOG.get(slug, (slug.upper(), "", "", "%"))
    out = dict(_MOCK_LAST_VALUE)
    out["slug"] = slug
    out["name"] = meta[0]
    return out


def _mock_monthly_matrix(slug=""):
    from data_sources.ddm.inflation.catalog import INDEX_CATALOG
    meta = INDEX_CATALOG.get(slug, (slug.upper(), "", "", "%"))
    out = dict(_MOCK_MATRIX)
    out["slug"] = slug
    out["name"] = meta[0]
    return out


def _patch_query(monkeypatch):
    """Patch query_engine functions at the source module + the dashboard
    namespace (local refs bound at import time)."""
    import data_sources.ddm.inflation.query_engine as qe
    monkeypatch.setattr(qe, "index_history", _mock_index_history)
    monkeypatch.setattr(qe, "last_value", _mock_last_value)
    monkeypatch.setattr(qe, "monthly_matrix", _mock_monthly_matrix)

    from skills.ddm.inflation.modes import dashboard
    monkeypatch.setattr(dashboard, "index_history", _mock_index_history)
    monkeypatch.setattr(dashboard, "last_value", _mock_last_value)
    monkeypatch.setattr(dashboard, "monthly_matrix", _mock_monthly_matrix)


def test_dashboard_has_4_tabs(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)
    assert res["status"] == "ok"
    tab_names = [t["name"] for t in res["tabs"]]
    assert tab_names == ["IGP-M", "IPCA", "INPC", "Comparativo"]


def test_dashboard_uses_name_not_label(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)
    for t in res["tabs"]:
        assert "name" in t
        assert "label" not in t


def test_dashboard_kpis_at_top_level(monkeypatch):
    """KPIs are at top level (not per-tab)."""
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)
    assert "kpis" in res
    # 3 KPIs per index tab * 3 index tabs = 9 KPIs (Comparativo has none).
    assert len(res["kpis"]) == 9
    # Tabs should NOT have per-tab kpis (the helper uses _kpis which is
    # popped before the tab dict is appended).
    for t in res["tabs"]:
        assert "kpis" not in t
        assert "_kpis" not in t


def test_index_tabs_have_kpis_chart_table_matrix(monkeypatch):
    """Each per-index tab has subtabs with chart + table (Historico) + heatmap (Matriz)."""
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"][:3]:  # IGP-M, IPCA, INPC
        # v3: each tab is ONE section of type="subtabs" with 2 subtabs
        assert len(tab["sections"]) == 1, f"{tab['name']}: expected 1 section"
        sub = tab["sections"][0]
        assert sub["type"] == "subtabs", f"{tab['name']}: expected subtabs"
        subtab_names = [s["name"] for s in sub["tabs"]]
        assert "Histórico" in subtab_names or "Historico" in subtab_names
        assert "Matriz" in subtab_names

        # Historico subtab: chart + table
        hist = sub["tabs"][0]
        hist_types = [s["type"] for s in hist["sections"]]
        assert "chart" in hist_types, f"{tab['name']}: missing chart in Historico"
        assert "table" in hist_types, f"{tab['name']}: missing table in Historico"

        # Matriz subtab: heatmap
        mat = sub["tabs"][1]
        mat_types = [s["type"] for s in mat["sections"]]
        assert "heatmap" in mat_types, f"{tab['name']}: missing heatmap in Matriz"


def test_comparativo_tab_has_no_tables(monkeypatch):
    """Comparativo tab is chart-only (NO tables)."""
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    cmp_tab = res["tabs"][-1]
    assert cmp_tab["name"] == "Comparativo"
    section_types = [s["type"] for s in cmp_tab["sections"]]
    assert "table" not in section_types
    assert "chart" in section_types


def test_chart_sections_emit_chart_data(monkeypatch):
    """v3 fix: chart sections emit Chart.js config in `chart_data`."""
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"]:
        chart_secs = [s for s in tab["sections"] if s.get("type") == "chart"]
        for cs in chart_secs:
            assert "chart_data" in cs
            assert "labels" not in cs  # moved inside chart_data
            assert cs["chart_data"]["type"] == "line"
            assert "datasets" in cs["chart_data"]["data"]


def test_table_sections_have_column_align(monkeypatch):
    """Tables that include numeric columns carry a `column_align` hint."""
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"][:3]:
        table_secs = [s for s in tab["sections"] if s.get("type") == "table"]
        for ts in table_secs:
            assert "column_align" in ts
            assert ts["column_align"][0] == "left"
            # All columns after the first should be right-aligned.
            assert all(a == "right" for a in ts["column_align"][1:])


def test_kpis_are_formatted_as_pct(monkeypatch):
    """KPI values are formatted as PT-BR percentages (comma decimal)."""
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    # The first KPI is "IGP-M (mes)" with value -1.16.
    first = res["kpis"][0]
    assert first["label"] == "IGP-M (mes)"
    assert first["value"] == "-1,16%"
    assert first["raw"] == -1.16


def test_comparativo_overlay_has_3_datasets(monkeypatch):
    """Comparativo overlay chart has one dataset per index (3 total)."""
    _patch_query(monkeypatch)
    from skills.ddm.inflation.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    cmp_tab = res["tabs"][-1]
    chart = next(s for s in cmp_tab["sections"] if s.get("type") == "chart")
    assert len(chart["chart_data"]["data"]["datasets"]) == 3
    labels = [ds["label"] for ds in chart["chart_data"]["data"]["datasets"]]
    assert any("IGP-M" in l for l in labels)
    assert any("IPCA" in l for l in labels)
    assert any("INPC" in l for l in labels)
