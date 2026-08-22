"""tests/skills/ddm/juros/test_dashboard.py - dashboard tests with mocked query_engine.

Mocks data_sources.ddm.juros.query_engine.juros_history + last_value +
monthly_matrix so no DB / HTTP access is needed. Verifies:
  - 4 tabs total: Selic, Meta Selic, CDI, Comparativo
  - Per-index tabs use type:"subtabs" with 2 subtabs (Historico + Matriz)
  - KPIs are at top level (not per-tab)
  - Per-index tabs have 3 KPIs (month_value, media_no_ano, media_12m)
  - Historico subtab chart has 3 datasets (not 2)
  - Matriz subtab has NO "Ano" column in the table
  - Comparativo tab has NO tables (chart only)
  - Chart sections emit Chart.js config in `chart_data`
"""
from __future__ import annotations


_MOCK_HISTORY = [
    {"ref_date": "2026-07", "month_value": 10.50,
     "media_no_ano": 11.32, "media_12m": 11.45},
    {"ref_date": "2026-06", "month_value": 10.50,
     "media_no_ano": 11.29, "media_12m": 11.50},
    {"ref_date": "2026-05", "month_value": 10.50,
     "media_no_ano": 11.25, "media_12m": 11.55},
]


_MOCK_LAST_VALUE = {
    "status": "ok", "slug": "", "name": "", "unit": "% a.a.",
    "ref_date": "2026-07", "month_value": 10.50,
    "media_no_ano": 11.32, "media_12m": 11.45,
}


_MOCK_MATRIX = {
    "status": "ok", "slug": "", "name": "", "unit": "% a.a.",
    "years": [2026, 2025],
    "months": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
    "matrix": {
        2026: {"Jan": 13.15, "Fev": 12.85, "Mar": 11.25, "Abr": 10.50,
               "Mai": 10.50, "Jun": 10.50, "Jul": 10.50,
               "Ago": None, "Set": None, "Out": None,
               "Nov": None, "Dez": None},
        2025: {"Jan": 12.15, "Fev": 12.25, "Mar": 11.75, "Abr": 11.25,
               "Mai": 11.25, "Jun": 11.25, "Jul": 11.25, "Ago": 11.25,
               "Set": 11.25, "Out": 11.75, "Nov": 12.25, "Dez": 12.75},
    },
}


def _mock_juros_history(slug="", limit=60):
    from data_sources.ddm.juros.catalog import JUROS_CATALOG
    meta = JUROS_CATALOG.get(slug, (slug.upper(), "", "", "% a.a."))
    return {
        "status": "ok", "slug": slug, "name": meta[0], "unit": "% a.a.",
        "count": len(_MOCK_HISTORY), "observations": list(_MOCK_HISTORY),
    }


def _mock_last_value(slug=""):
    from data_sources.ddm.juros.catalog import JUROS_CATALOG
    meta = JUROS_CATALOG.get(slug, (slug.upper(), "", "", "% a.a."))
    out = dict(_MOCK_LAST_VALUE)
    out["slug"] = slug
    out["name"] = meta[0]
    return out


def _mock_monthly_matrix(slug=""):
    from data_sources.ddm.juros.catalog import JUROS_CATALOG
    meta = JUROS_CATALOG.get(slug, (slug.upper(), "", "", "% a.a."))
    out = dict(_MOCK_MATRIX)
    out["slug"] = slug
    out["name"] = meta[0]
    return out


def _patch_query(monkeypatch):
    """Patch query_engine functions at the source module + the dashboard
    namespace (local refs bound at import time)."""
    import data_sources.ddm.juros.query_engine as qe
    monkeypatch.setattr(qe, "juros_history", _mock_juros_history)
    monkeypatch.setattr(qe, "last_value", _mock_last_value)
    monkeypatch.setattr(qe, "monthly_matrix", _mock_monthly_matrix)

    from skills.ddm.juros.modes import dashboard
    monkeypatch.setattr(dashboard, "juros_history", _mock_juros_history)
    monkeypatch.setattr(dashboard, "last_value", _mock_last_value)
    monkeypatch.setattr(dashboard, "monthly_matrix", _mock_monthly_matrix)


def test_dashboard_has_4_tabs(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)
    assert res["status"] == "ok"
    tab_names = [t["name"] for t in res["tabs"]]
    assert tab_names == ["Selic", "Meta Selic", "CDI", "Comparativo"]


def test_dashboard_uses_name_not_label(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)
    for t in res["tabs"]:
        assert "name" in t
        assert "label" not in t


def test_dashboard_kpis_at_top_level(monkeypatch):
    """KPIs are at top level (not per-tab).

    Each per-index tab produces 3 KPIs (month_value, media_no_ano,
    media_12m). 3 index tabs * 3 KPIs = 9 total (Comparativo has none)."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)
    assert "kpis" in res
    assert len(res["kpis"]) == 9
    for t in res["tabs"]:
        assert "kpis" not in t
        assert "_kpis" not in t


def test_index_tabs_use_subtabs(monkeypatch):
    """Each per-index tab has ONE section of type:"subtabs" with 2 subtabs."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"][:3]:  # Selic, Meta Selic, CDI
        assert len(tab["sections"]) == 1, f"{tab['name']}: expected 1 section"
        sub = tab["sections"][0]
        assert sub["type"] == "subtabs"
        subtab_names = [s["name"] for s in sub["tabs"]]
        assert subtab_names == ["Historico", "Matriz"]


def test_historico_subtab_has_chart_with_3_datasets(monkeypatch):
    """Historico subtab chart has 3 datasets (month_value + media_no_ano +
    media_12m), NOT 2."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"][:3]:
        sub = tab["sections"][0]
        hist = sub["tabs"][0]  # Historico
        charts = [s for s in hist["sections"] if s.get("type") == "chart"]
        assert len(charts) == 1, f"{tab['name']}: missing historico chart"
        ds = charts[0]["chart_data"]["data"]["datasets"]
        assert len(ds) == 3
        labels = [d["label"] for d in ds]
        assert any("Indice do mes" in l for l in labels)
        assert any("Media no ano" in l for l in labels)
        assert any("Media 12 meses" in l for l in labels)


def test_historico_subtab_has_table_with_4_columns(monkeypatch):
    """Historico subtab table has 4 columns: Mes/Ano | Indice do mes (%) |
    Media no ano (%) | Media 12 meses (%)."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"][:3]:
        sub = tab["sections"][0]
        hist = sub["tabs"][0]
        tables = [s for s in hist["sections"] if s.get("type") == "table"]
        assert len(tables) == 1, f"{tab['name']}: missing historico table"
        assert tables[0]["columns"] == [
            "Mes/Ano", "Indice do mes (%)",
            "Media no ano (%)", "Media 12 meses (%)",
        ]


def test_matriz_subtab_has_no_ano_column(monkeypatch):
    """Matriz subtab table has 12 month columns only - NO 'Ano' column."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"][:3]:
        sub = tab["sections"][0]
        matriz = sub["tabs"][1]  # Matriz
        heatmaps = [s for s in matriz["sections"] if s.get("type") == "heatmap"]
        assert len(heatmaps) == 1, f"{tab['name']}: missing matriz heatmap"
        cols = heatmaps[0]["columns"]
        assert cols[0] == "Ano"  # year-label column (corner)
        # The remaining 12 columns should be Jan..Dez (no trailing "Ano").
        assert "Ano" not in cols[1:]
        assert cols[1:] == ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def test_matriz_subtab_has_heatmap_cells(monkeypatch):
    """Matriz heatmap cells are {text, bg, color} dicts (NOT plain strings)."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    for tab in res["tabs"][:3]:
        sub = tab["sections"][0]
        matriz = sub["tabs"][1]
        heatmaps = [s for s in matriz["sections"] if s.get("type") == "heatmap"]
        assert len(heatmaps) == 1
        rows = heatmaps[0]["rows"]
        assert len(rows) > 0
        # First cell is the year (string), rest are {text, bg, color} dicts
        assert isinstance(rows[0][0], str)  # year label
        if len(rows[0]) > 1:
            cell = rows[0][1]  # first month cell
            assert isinstance(cell, dict), f"expected dict, got {type(cell)}"
            assert "text" in cell
            assert "bg" in cell
            assert "color" in cell


def test_comparativo_tab_has_no_tables(monkeypatch):
    """Comparativo tab is chart-only (NO tables)."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    cmp_tab = res["tabs"][-1]
    assert cmp_tab["name"] == "Comparativo"
    section_types = [s["type"] for s in cmp_tab["sections"]]
    assert "table" not in section_types
    assert "subtabs" not in section_types
    assert "chart" in section_types


def test_chart_sections_emit_chart_data(monkeypatch):
    """Chart sections emit Chart.js config in `chart_data`."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    # Walk every section, including inside subtabs.
    chart_secs = []
    for tab in res["tabs"]:
        for s in tab["sections"]:
            if s.get("type") == "subtabs":
                for sub in s.get("tabs", []):
                    chart_secs.extend(
                        ss for ss in sub.get("sections", [])
                        if ss.get("type") == "chart"
                    )
            elif s.get("type") == "chart":
                chart_secs.append(s)
    assert len(chart_secs) >= 4  # 3 historico + 1 comparativo
    for cs in chart_secs:
        assert "chart_data" in cs
        assert "labels" not in cs  # moved inside chart_data
        assert cs["chart_data"]["type"] == "line"
        assert "datasets" in cs["chart_data"]["data"]


def test_kpis_are_formatted_as_pct(monkeypatch):
    """KPI values are formatted as PT-BR percentages (comma decimal)."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    # The first KPI is "Selic (mes)" with value 10.50.
    first = res["kpis"][0]
    assert first["label"] == "Selic (mes)"
    assert first["value"] == "10,50%"
    assert first["raw"] == 10.50


def test_comparativo_overlay_has_3_datasets(monkeypatch):
    """Comparativo overlay chart has one dataset per index (3 total)."""
    _patch_query(monkeypatch)
    from skills.ddm.juros.modes import dashboard
    res = dashboard.dashboard(months=12, compare_months=12)

    cmp_tab = res["tabs"][-1]
    chart = next(s for s in cmp_tab["sections"] if s.get("type") == "chart")
    assert len(chart["chart_data"]["data"]["datasets"]) == 3
    labels = [ds["label"] for ds in chart["chart_data"]["data"]["datasets"]]
    assert any("Selic" in l for l in labels)
    assert any("Meta Selic" in l for l in labels)
    assert any("CDI" in l for l in labels)
