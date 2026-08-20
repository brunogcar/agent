"""tests/skills/ddm/poupanca/test_dashboard.py - dashboard tests with mocked query_engine.

Mocks data_sources.ddm.poupanca.query_engine.poupanca_history + last_value +
monthly_matrix so no DB / HTTP access is needed. Verifies:
  - 1 tab total: Poupanca (NO Comparativo tab - only 1 index)
  - The tab uses type:"subtabs" with 2 subtabs (Historico + Matriz)
  - KPIs are at top level (not per-tab)
  - The tab has 3 KPIs (month_value, acumulado_no_ano, acumulado_12m)
  - Historico subtab chart has 3 datasets (not 2)
  - Historico subtab table has 4 columns + negative_red=True
  - Matriz subtab returns type="heatmap" with {text, bg, color} cell dicts
  - Matriz subtab has NO trailing "Ano" column in the table
  - Section titles do NOT repeat the index name (already in the tab name)
  - Chart sections emit Chart.js config in `chart_data`
"""
from __future__ import annotations


_MOCK_HISTORY = [
    {"ref_date": "2026-07", "month_value": 0.58,
     "acumulado_no_ano": 4.26, "acumulado_12m": 7.74},
    {"ref_date": "2026-06", "month_value": 0.58,
     "acumulado_no_ano": 3.68, "acumulado_12m": 7.71},
    {"ref_date": "2026-05", "month_value": 0.58,
     "acumulado_no_ano": 3.10, "acumulado_12m": 7.67},
]


_MOCK_LAST_VALUE = {
    "status": "ok", "slug": "", "name": "", "unit": "%",
    "ref_date": "2026-07", "month_value": 0.58,
    "acumulado_no_ano": 4.26, "acumulado_12m": 7.74,
}


_MOCK_MATRIX = {
    "status": "ok", "slug": "", "name": "", "unit": "%",
    "years": [2026, 2025],
    "months": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
    "matrix": {
        2026: {"Jan": 0.67, "Fev": 0.65, "Mar": 0.62, "Abr": 0.58,
               "Mai": 0.58, "Jun": 0.58, "Jul": 0.58,
               "Ago": None, "Set": None, "Out": None,
               "Nov": None, "Dez": None},
        2025: {"Jan": 0.55, "Fev": 0.56, "Mar": 0.58, "Abr": 0.60,
               "Mai": 0.62, "Jun": 0.65, "Jul": 0.67, "Ago": 0.70,
               "Set": 0.72, "Out": 0.73, "Nov": 0.74, "Dez": 0.75},
    },
}


def _mock_poupanca_history(slug="", limit=60):
    from data_sources.ddm.poupanca.catalog import POUPANCA_CATALOG
    meta = POUPANCA_CATALOG.get(slug, (slug.upper(), "", "", "%"))
    return {
        "status": "ok", "slug": slug, "name": meta[0], "unit": "%",
        "count": len(_MOCK_HISTORY), "observations": list(_MOCK_HISTORY),
    }


def _mock_last_value(slug=""):
    from data_sources.ddm.poupanca.catalog import POUPANCA_CATALOG
    meta = POUPANCA_CATALOG.get(slug, (slug.upper(), "", "", "%"))
    out = dict(_MOCK_LAST_VALUE)
    out["slug"] = slug
    out["name"] = meta[0]
    return out


def _mock_monthly_matrix(slug=""):
    from data_sources.ddm.poupanca.catalog import POUPANCA_CATALOG
    meta = POUPANCA_CATALOG.get(slug, (slug.upper(), "", "", "%"))
    out = dict(_MOCK_MATRIX)
    out["slug"] = slug
    out["name"] = meta[0]
    return out


def _patch_query(monkeypatch):
    """Patch query_engine functions at the source module + the dashboard
    namespace (local refs bound at import time)."""
    import data_sources.ddm.poupanca.query_engine as qe
    monkeypatch.setattr(qe, "poupanca_history", _mock_poupanca_history)
    monkeypatch.setattr(qe, "last_value", _mock_last_value)
    monkeypatch.setattr(qe, "monthly_matrix", _mock_monthly_matrix)

    from skills.ddm.poupanca.modes import dashboard
    monkeypatch.setattr(dashboard, "poupanca_history", _mock_poupanca_history)
    monkeypatch.setattr(dashboard, "last_value", _mock_last_value)
    monkeypatch.setattr(dashboard, "monthly_matrix", _mock_monthly_matrix)


def test_dashboard_has_1_tab(monkeypatch):
    """Dashboard has exactly 1 tab: Poupanca (NO Comparativo)."""
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)
    assert res["status"] == "ok"
    tab_names = [t["name"] for t in res["tabs"]]
    assert tab_names == ["Poupanca"]


def test_dashboard_uses_name_not_label(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)
    for t in res["tabs"]:
        assert "name" in t
        assert "label" not in t


def test_dashboard_kpis_at_top_level(monkeypatch):
    """KPIs are at top level (not per-tab).

    The Poupanca tab produces 3 KPIs (month_value, acumulado_no_ano,
    acumulado_12m). 1 index tab * 3 KPIs = 3 total."""
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)
    assert "kpis" in res
    assert len(res["kpis"]) == 3
    for t in res["tabs"]:
        assert "kpis" not in t
        assert "_kpis" not in t


def test_index_tab_uses_subtabs(monkeypatch):
    """The Poupanca tab has ONE section of type:"subtabs" with 2 subtabs."""
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    tab = res["tabs"][0]
    assert tab["name"] == "Poupanca"
    assert tab["group"] == "Renda Fixa"
    assert len(tab["sections"]) == 1, "expected 1 section"
    sub = tab["sections"][0]
    assert sub["type"] == "subtabs"
    subtab_names = [s["name"] for s in sub["tabs"]]
    assert subtab_names == ["Historico", "Matriz"]


def test_historico_subtab_has_chart_with_3_datasets(monkeypatch):
    """Historico subtab chart has 3 datasets (month_value + acumulado_no_ano
    + acumulado_12m), NOT 2."""
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    tab = res["tabs"][0]
    sub = tab["sections"][0]
    hist = sub["tabs"][0]  # Historico
    charts = [s for s in hist["sections"] if s.get("type") == "chart"]
    assert len(charts) == 1, "missing historico chart"
    ds = charts[0]["chart_data"]["data"]["datasets"]
    assert len(ds) == 3
    labels = [d["label"] for d in ds]
    assert any("Rendimento" in l for l in labels)
    assert any("Acumulado no ano" in l for l in labels)
    assert any("Acumulado 12" in l for l in labels)


def test_historico_subtab_has_table_with_4_columns_and_negative_red(monkeypatch):
    """Historico subtab table has 4 columns: Mes/Ano | Rendimento (%) |
    Acumulado no ano (%) | Acumulado 12m (%), with negative_red=True."""
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    tab = res["tabs"][0]
    sub = tab["sections"][0]
    hist = sub["tabs"][0]
    tables = [s for s in hist["sections"] if s.get("type") == "table"]
    assert len(tables) == 1, "missing historico table"
    assert tables[0]["columns"] == [
        "Mes/Ano", "Rendimento (%)",
        "Acumulado no ano (%)", "Acumulado 12m (%)",
    ]
    assert tables[0].get("negative_red") is True


def test_matriz_subtab_returns_type_heatmap(monkeypatch):
    """Matriz subtab section type is "heatmap" (NOT "table").

    This was the bug fix in juros v4 that poupanca inherits from day one.
    The heatmap_table macro expects type="heatmap" with {text, bg, color}
    cell dicts.
    """
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    tab = res["tabs"][0]
    sub = tab["sections"][0]
    matriz = sub["tabs"][1]  # Matriz
    sections = matriz["sections"]
    assert len(sections) == 1, "missing matriz section"
    assert sections[0]["type"] == "heatmap"


def test_matriz_subtab_has_no_ano_column(monkeypatch):
    """Matriz subtab table has 12 month columns only - NO trailing 'Ano' column.

    The first column is "Ano" (the year-label corner), but no trailing
    "Ano" acumulado column.
    """
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    tab = res["tabs"][0]
    sub = tab["sections"][0]
    matriz = sub["tabs"][1]
    sections = matriz["sections"]
    cols = sections[0]["columns"]
    assert cols[0] == "Ano"  # year-label column (corner)
    # The remaining 12 columns should be Jan..Dez (no trailing "Ano").
    assert "Ano" not in cols[1:]
    assert cols[1:] == ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                        "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def test_matriz_subtab_cells_are_dicts(monkeypatch):
    """Each matrix cell is a dict {text, bg, color} (NOT a string).

    This was the bug fix in juros v4 (_heat_color returning a string) that
    poupanca inherits from day one.
    """
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    tab = res["tabs"][0]
    sub = tab["sections"][0]
    matriz = sub["tabs"][1]
    section = matriz["sections"][0]
    rows = section["rows"]
    assert len(rows) == 2  # 2 years

    # First row = 2026. First cell = "2026" (year label). Cells 1..12 = months.
    # (Jan=row[1], Fev=row[2], ..., Ago=row[8], ..., Dez=row[12]).
    row_2026 = rows[0]
    assert row_2026[0] == "2026"
    # Jan/2026 has value 0.67 -> dict {text, bg, color}.
    jan_cell = row_2026[1]
    assert isinstance(jan_cell, dict), f"expected dict, got {type(jan_cell)}"
    assert set(jan_cell.keys()) == {"text", "bg", "color"}
    assert jan_cell["text"] == "0,67"
    assert jan_cell["bg"].startswith("#")
    assert jan_cell["color"] in ("#000", "#fff")

    # Aug-Dec 2026 are None -> dict {text: "-", bg: "", color: ""}.
    aug_cell = row_2026[8]  # Aug is index 8 (year=0, Jan=1, ..., Ago=8)
    assert isinstance(aug_cell, dict)
    assert aug_cell == {"text": "-", "bg": "", "color": ""}


def test_chart_sections_emit_chart_data(monkeypatch):
    """Chart sections emit Chart.js config in `chart_data`."""
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

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
    assert len(chart_secs) == 1  # 1 historico chart (no Comparativo)
    for cs in chart_secs:
        assert "chart_data" in cs
        assert "labels" not in cs  # moved inside chart_data
        assert cs["chart_data"]["type"] == "line"
        assert "datasets" in cs["chart_data"]["data"]


def test_kpis_are_formatted_as_pct(monkeypatch):
    """KPI values are formatted as PT-BR percentages (comma decimal)."""
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    # The first KPI is "Poupanca (mes)" with value 0.58.
    first = res["kpis"][0]
    assert first["label"] == "Poupanca (mes)"
    assert first["value"] == "0,58%"
    assert first["raw"] == 0.58


def test_section_titles_dont_repeat_index_name(monkeypatch):
    """Section titles do NOT prefix with the index name (already in tab name).

    Juros v1 used "Selic - evolucao mensal" etc; the poupanca task spec
    requires titles without the prefix ("Evolucao mensal", "Historico mensal",
    "Matriz mensal").
    """
    _patch_query(monkeypatch)
    from skills.ddm.poupanca.modes import dashboard
    res = dashboard.dashboard(months=12)

    tab = res["tabs"][0]
    sub = tab["sections"][0]

    hist = sub["tabs"][0]
    chart = next(s for s in hist["sections"] if s.get("type") == "chart")
    table = next(s for s in hist["sections"] if s.get("type") == "table")
    assert chart["title"] == "Evolucao mensal"
    assert table["title"] == "Historico mensal"

    matriz = sub["tabs"][1]
    matrix_sec = next(s for s in matriz["sections"] if s.get("type") == "heatmap")
    assert matrix_sec["title"] == "Matriz mensal"
