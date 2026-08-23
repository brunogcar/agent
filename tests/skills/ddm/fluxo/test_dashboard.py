"""tests/skills/ddm/fluxo/test_dashboard.py - dashboard tests with mocked query_engine.

Mocks data_sources.ddm.fluxo.query_engine.fluxo_data + summary +
monthly_cumulative + annual_cumulative so no DB / HTTP access is needed.

Verifies:
  - 5 tabs total: 1 Fluxo (group: Fluxo) + 4 investor tabs (group: Investidores)
  - Fluxo tab has chart + sortable table
  - Each investor tab has 3 subtabs (Diario / Mensal / Anual)
  - Diario subtab has bar chart + table
  - Mensal subtab has line chart + table
  - Anual subtab has line chart + table
  - KPIs are at top level (5 KPIs: 1 date + 4 investor totals)
  - Fluxo table has sortable=True + default_sort by Data DESC
  - Investor table has sortable=True + default_sort by Data DESC
  - Both tables have negative_red=True
  - Chart has 4 datasets (Estrangeiro, Institucional, Pessoa fisica, Inst. Financeira)
  - Daily investor chart has 1 dataset with green/red per-bar colors
  - Range selector enabled on Fluxo chart + Diario + Anual charts
"""
from __future__ import annotations


# 4 investors matching the per-investor tabs.
_INVESTORS = [
    ("estrangeiro",     "Estrangeiro"),
    ("institucional",   "Institucional"),
    ("pessoa_fisica",   "Pessoa fisica"),
    ("inst_financeira", "Inst. Financeira"),
]


def _mock_obs(d: str, ext: float, inst: float, pf: float, fin: float) -> dict:
    """Build a mock observation dict for one ref_date."""
    return {
        "ref_date":        d,
        "estrangeiro":     ext,
        "institucional":   inst,
        "pessoa_fisica":   pf,
        "inst_financeira": fin,
        "outros":          10.0,
        "synced_at":       "2026-08-19T12:00:00+00:00",
    }


def _mock_observations() -> list[dict]:
    """Return a synthetic daily series covering 3 trading days."""
    return [
        _mock_obs("2026-08-17", -496.07,   71.25, 154.80, 181.58),
        _mock_obs("2026-08-18", -1782.10, 1362.50, 357.75,  -9.69),
        _mock_obs("2026-08-19", -1582.35, 1029.81,  42.36, 519.49),
    ]


def _mock_fluxo_data(limit: int = 0):
    return {
        "status":      "ok",
        "count":       3,
        "synced_at":   "2026-08-19T12:00:00+00:00",
        "observations": _mock_observations(),
    }


def _mock_summary():
    return {
        "status":      "ok",
        "row_count":   3,
        "first_date":  "2026-08-17",
        "last_date":   "2026-08-19",
        "synced_at":   "2026-08-19T12:00:00+00:00",
        "sync_rows":   3,
    }


def _mock_monthly_cumulative(investor: str = ""):
    return {
        "status":      "ok",
        "investor":    investor,
        "count":       1,
        "observations": [
            {"month": "2026-08", "label": "Ago/2026", "value": -3860.52},
        ],
    }


def _mock_annual_cumulative(investor: str = ""):
    return {
        "status":      "ok",
        "investor":    investor,
        "count":       3,
        "observations": [
            {"ref_date": "2026-08-17", "value": -496.07},
            {"ref_date": "2026-08-18", "value": -2278.17},
            {"ref_date": "2026-08-19", "value": -3860.52},
        ],
    }


def _patch_query(monkeypatch):
    """Patch query_engine functions at the source module + the dashboard
    namespace (local refs bound at import time)."""
    import data_sources.ddm.fluxo.query_engine as qe
    monkeypatch.setattr(qe, "fluxo_data", _mock_fluxo_data)
    monkeypatch.setattr(qe, "summary", _mock_summary)
    monkeypatch.setattr(qe, "monthly_cumulative", _mock_monthly_cumulative)
    monkeypatch.setattr(qe, "annual_cumulative", _mock_annual_cumulative)

    from skills.ddm.fluxo.modes import dashboard
    monkeypatch.setattr(dashboard, "fluxo_data", _mock_fluxo_data)
    monkeypatch.setattr(dashboard, "summary", _mock_summary)
    monkeypatch.setattr(dashboard, "monthly_cumulative", _mock_monthly_cumulative)
    monkeypatch.setattr(dashboard, "annual_cumulative", _mock_annual_cumulative)


# ────────────────────────────────────────────────────────────────────────
# Tab structure tests
# ────────────────────────────────────────────────────────────────────────

def test_dashboard_has_5_tabs(monkeypatch):
    """1 Fluxo tab + 4 investor tabs = 5 tabs total."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    assert res["status"] == "ok"
    assert len(res["tabs"]) == 5


def test_dashboard_tab_names(monkeypatch):
    """First tab is 'Fluxo', the rest match the investor list."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    tab_names = [t["name"] for t in res["tabs"]]
    assert tab_names[0] == "Fluxo"
    for _, label in _INVESTORS:
        assert label in tab_names


def test_dashboard_fluxo_tab_group(monkeypatch):
    """The Fluxo tab is in group 'Fluxo'."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    assert res["tabs"][0]["group"] == "Fluxo"


def test_dashboard_investor_tabs_group(monkeypatch):
    """All investor tabs are in group 'Investidores'."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    for tab in res["tabs"][1:]:
        assert tab["group"] == "Investidores"


def test_dashboard_fluxo_tab_has_chart_and_table(monkeypatch):
    """Fluxo tab has 1 chart + 1 table."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    fluxo_tab = res["tabs"][0]
    charts = [s for s in fluxo_tab["sections"] if s.get("type") == "chart"]
    tables = [s for s in fluxo_tab["sections"] if s.get("type") == "table"]
    assert len(charts) == 1
    assert len(tables) == 1


def test_dashboard_investor_tab_has_3_subtabs(monkeypatch):
    """Each investor tab has 3 subtabs (Diario / Mensal / Anual)."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    # Inspect the Estrangeiro tab (2nd tab overall).
    est_tab = res["tabs"][1]
    assert est_tab["name"] == "Estrangeiro"
    subtabs_sections = [s for s in est_tab["sections"]
                        if s.get("type") == "subtabs"]
    assert len(subtabs_sections) == 1
    subtab_names = [t["name"] for t in subtabs_sections[0]["tabs"]]
    assert subtab_names == ["Diario", "Mensal", "Anual"]


def test_dashboard_daily_subtab_has_chart_and_table(monkeypatch):
    """The Diario subtab has 1 chart + 1 table."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    est_tab = res["tabs"][1]
    subtabs = next(s for s in est_tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    daily_subtab = next(t for t in subtabs if t["name"] == "Diario")
    charts = [s for s in daily_subtab["sections"] if s.get("type") == "chart"]
    tables = [s for s in daily_subtab["sections"] if s.get("type") == "table"]
    assert len(charts) == 1
    assert len(tables) == 1


def test_dashboard_monthly_subtab_has_chart_and_table(monkeypatch):
    """The Mensal subtab has 1 chart + 1 table."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    est_tab = res["tabs"][1]
    subtabs = next(s for s in est_tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    monthly_subtab = next(t for t in subtabs if t["name"] == "Mensal")
    charts = [s for s in monthly_subtab["sections"] if s.get("type") == "chart"]
    tables = [s for s in monthly_subtab["sections"] if s.get("type") == "table"]
    assert len(charts) == 1
    assert len(tables) == 1


def test_dashboard_annual_subtab_has_chart_and_table(monkeypatch):
    """The Anual subtab has 1 chart + 1 table."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    est_tab = res["tabs"][1]
    subtabs = next(s for s in est_tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    annual_subtab = next(t for t in subtabs if t["name"] == "Anual")
    charts = [s for s in annual_subtab["sections"] if s.get("type") == "chart"]
    tables = [s for s in annual_subtab["sections"] if s.get("type") == "table"]
    assert len(charts) == 1
    assert len(tables) == 1


# ────────────────────────────────────────────────────────────────────────
# KPI tests
# ────────────────────────────────────────────────────────────────────────

def test_dashboard_kpis_at_top_level(monkeypatch):
    """KPIs are at top level (not per-tab)."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    assert "kpis" in res
    # 1 date KPI + 4 investor-total KPIs = 5 KPIs.
    assert len(res["kpis"]) == 5
    for t in res["tabs"]:
        assert "kpis" not in t


def test_dashboard_kpis_have_expected_labels(monkeypatch):
    """KPIs include 'Ultima data' + 4 investor totals."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    labels = [k["label"] for k in res["kpis"]]
    assert "Ultima data" in labels
    for _, label in _INVESTORS:
        assert f"Total {label}" in labels


# ────────────────────────────────────────────────────────────────────────
# Fluxo table tests
# ────────────────────────────────────────────────────────────────────────

def _get_fluxo_table(monkeypatch) -> dict:
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    fluxo_tab = res["tabs"][0]
    return next(s for s in fluxo_tab["sections"] if s.get("type") == "table")


def test_fluxo_table_is_sortable(monkeypatch):
    """Fluxo table is sortable with default sort by Data DESC (col 0)."""
    table = _get_fluxo_table(monkeypatch)
    assert table.get("sortable") is True
    assert table.get("default_sort") == {"column": 0, "direction": "desc"}


def test_fluxo_table_has_negative_red(monkeypatch):
    """Fluxo table has negative_red=True."""
    table = _get_fluxo_table(monkeypatch)
    assert table.get("negative_red") is True


def test_fluxo_table_columns(monkeypatch):
    """Fluxo table has 6 columns: Data + 5 investors."""
    table = _get_fluxo_table(monkeypatch)
    assert table["columns"] == [
        "Data", "Estrangeiro", "Institucional", "Pessoa fisica",
        "Inst. Financeira", "Outros",
    ]


def test_fluxo_table_column_align(monkeypatch):
    """Fluxo table alignment: left | right | right | right | right | right."""
    table = _get_fluxo_table(monkeypatch)
    assert table["column_align"] == [
        "left", "right", "right", "right", "right", "right",
    ]


def test_fluxo_table_sort_types(monkeypatch):
    """Fluxo table sort types: text | number | number | number | number | number."""
    table = _get_fluxo_table(monkeypatch)
    assert table["sort_types"] == [
        "text", "number", "number", "number", "number", "number",
    ]


def test_fluxo_table_value_cells_have_data_value(monkeypatch):
    """Numeric value cells are dicts with text + data-value attributes."""
    table = _get_fluxo_table(monkeypatch)
    first_row = table["rows"][0]
    # First cell = date (dict with text + data-value).
    assert isinstance(first_row[0], dict)
    assert "text" in first_row[0]
    assert "data-value" in first_row[0]
    # Value cells (cols 1-5) are dicts.
    for i in (1, 2, 3, 4, 5):
        assert isinstance(first_row[i], dict)
        assert "text" in first_row[i]
        assert "data-value" in first_row[i]


def test_fluxo_table_date_cell_displays_pt_br(monkeypatch):
    """Date cells display as DD/MM/YYYY (PT-BR format).

    The dashboard's fluxo_data() returns observations ASC (oldest first),
    so the table's rows[0] is the oldest date (2026-08-17 in the mock).
    The default_sort = Data DESC will reorder the table on the client
    side via JS, but the raw HTML preserves the source order.
    """
    table = _get_fluxo_table(monkeypatch)
    first_row = table["rows"][0]
    date_cell = first_row[0]
    assert date_cell["text"] == "17/08/2026"
    assert date_cell["data-value"] == "2026-08-17"


def test_fluxo_table_value_cell_has_data_value(monkeypatch):
    """Numeric value cell carries the raw float in data-value (for sortTable)."""
    table = _get_fluxo_table(monkeypatch)
    first_row = table["rows"][0]
    # First row (oldest date 2026-08-17): estrangeiro = -496.07.
    estrangeiro_cell = first_row[1]
    assert estrangeiro_cell["text"].startswith("R$ ")
    assert estrangeiro_cell["data-value"] == "-496.070000"


# ────────────────────────────────────────────────────────────────────────
# Fluxo chart tests
# ────────────────────────────────────────────────────────────────────────

def _get_fluxo_chart(monkeypatch) -> dict:
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    fluxo_tab = res["tabs"][0]
    return next(s for s in fluxo_tab["sections"] if s.get("type") == "chart")


def test_fluxo_chart_has_4_datasets(monkeypatch):
    """Fluxo chart has 4 datasets (one per investor)."""
    chart = _get_fluxo_chart(monkeypatch)
    datasets = chart["chart_data"]["data"]["datasets"]
    assert len(datasets) == 4


def test_fluxo_chart_dataset_labels(monkeypatch):
    """Chart dataset labels are the 4 investor names."""
    chart = _get_fluxo_chart(monkeypatch)
    labels = [d["label"] for d in chart["chart_data"]["data"]["datasets"]]
    assert labels == ["Estrangeiro", "Institucional",
                      "Pessoa fisica", "Inst. Financeira"]


def test_fluxo_chart_dataset_colors(monkeypatch):
    """Chart dataset colors are blue / red / amber / green."""
    chart = _get_fluxo_chart(monkeypatch)
    colors = [d["backgroundColor"]
              for d in chart["chart_data"]["data"]["datasets"]]
    assert colors == ["#3b82f6", "#ef4444", "#f59e0b", "#22c55e"]


def test_fluxo_chart_type_is_bar(monkeypatch):
    """Chart type is 'bar'."""
    chart = _get_fluxo_chart(monkeypatch)
    assert chart["chart_data"]["type"] == "bar"


def test_fluxo_chart_has_range_selector(monkeypatch):
    """Fluxo chart has range selector enabled."""
    chart = _get_fluxo_chart(monkeypatch)
    assert chart.get("price_range_selector") is True
    assert "price_full_labels" in chart
    assert "price_full_datasets" in chart


# ────────────────────────────────────────────────────────────────────────
# Investor chart tests (Diario subtab)
# ────────────────────────────────────────────────────────────────────────

def _get_daily_chart(monkeypatch, investor_label: str) -> dict:
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    tab = next(t for t in res["tabs"] if t["name"] == investor_label)
    subtabs = next(s for s in tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    daily = next(t for t in subtabs if t["name"] == "Diario")
    return next(s for s in daily["sections"] if s.get("type") == "chart")


def test_daily_chart_has_1_dataset(monkeypatch):
    """Daily investor chart has 1 dataset."""
    chart = _get_daily_chart(monkeypatch, "Estrangeiro")
    datasets = chart["chart_data"]["data"]["datasets"]
    assert len(datasets) == 1


def test_daily_chart_dataset_label_is_investor(monkeypatch):
    """Daily chart dataset label matches the investor name."""
    chart = _get_daily_chart(monkeypatch, "Estrangeiro")
    assert chart["chart_data"]["data"]["datasets"][0]["label"] == "Estrangeiro"


def test_daily_chart_has_per_bar_colors(monkeypatch):
    """Daily chart has per-bar backgroundColor array (green + red)."""
    chart = _get_daily_chart(monkeypatch, "Estrangeiro")
    bg = chart["chart_data"]["data"]["datasets"][0]["backgroundColor"]
    assert isinstance(bg, list)
    assert len(bg) == 3  # 3 mock days
    # Estrangeiro mock values: -496.07, -1782.10, -1582.35 (all negative).
    # All bars should be red.
    assert all(c == "#ef4444" for c in bg)


def test_daily_chart_has_range_selector(monkeypatch):
    """Daily chart has range selector enabled."""
    chart = _get_daily_chart(monkeypatch, "Estrangeiro")
    assert chart.get("price_range_selector") is True


# ────────────────────────────────────────────────────────────────────────
# Investor table tests (Diario subtab)
# ────────────────────────────────────────────────────────────────────────

def _get_investor_table(monkeypatch, investor_label: str,
                        subtab_name: str = "Diario") -> dict:
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    tab = next(t for t in res["tabs"] if t["name"] == investor_label)
    subtabs = next(s for s in tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    subtab = next(t for t in subtabs if t["name"] == subtab_name)
    return next(s for s in subtab["sections"] if s.get("type") == "table")


def test_investor_table_is_sortable(monkeypatch):
    """Investor table is sortable with default sort by Data DESC."""
    table = _get_investor_table(monkeypatch, "Estrangeiro")
    assert table.get("sortable") is True
    assert table.get("default_sort") == {"column": 0, "direction": "desc"}


def test_investor_table_has_negative_red(monkeypatch):
    """Investor table has negative_red=True."""
    table = _get_investor_table(monkeypatch, "Estrangeiro")
    assert table.get("negative_red") is True


def test_investor_table_columns(monkeypatch):
    """Investor table has 2 columns: Data | Valor (mi)."""
    table = _get_investor_table(monkeypatch, "Estrangeiro")
    assert table["columns"] == ["Data", "Valor (mi)"]


def test_investor_table_column_align(monkeypatch):
    """Investor table alignment: left | right."""
    table = _get_investor_table(monkeypatch, "Estrangeiro")
    assert table["column_align"] == ["left", "right"]


def test_investor_table_sort_types(monkeypatch):
    """Investor table sort types: text | number."""
    table = _get_investor_table(monkeypatch, "Estrangeiro")
    assert table["sort_types"] == ["text", "number"]


# ────────────────────────────────────────────────────────────────────────
# Monthly + Annual chart tests
# ────────────────────────────────────────────────────────────────────────

def test_monthly_chart_is_line(monkeypatch):
    """Monthly chart is a line chart."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    est_tab = res["tabs"][1]
    subtabs = next(s for s in est_tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    monthly = next(t for t in subtabs if t["name"] == "Mensal")
    chart = next(s for s in monthly["sections"] if s.get("type") == "chart")
    assert chart["chart_data"]["type"] == "line"
    assert len(chart["chart_data"]["data"]["datasets"]) == 1


def test_annual_chart_is_line(monkeypatch):
    """Annual chart is a line chart."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    est_tab = res["tabs"][1]
    subtabs = next(s for s in est_tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    annual = next(t for t in subtabs if t["name"] == "Anual")
    chart = next(s for s in annual["sections"] if s.get("type") == "chart")
    assert chart["chart_data"]["type"] == "line"
    assert len(chart["chart_data"]["data"]["datasets"]) == 1


def test_annual_chart_has_range_selector(monkeypatch):
    """Annual chart has range selector enabled."""
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    est_tab = res["tabs"][1]
    subtabs = next(s for s in est_tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    annual = next(t for t in subtabs if t["name"] == "Anual")
    chart = next(s for s in annual["sections"] if s.get("type") == "chart")
    assert chart.get("price_range_selector") is True


# ────────────────────────────────────────────────────────────────────────
# [v3] Overlapping bar chart (Fluxo diario por investidor)
# ────────────────────────────────────────────────────────────────────────
# The reference chart (Fluxo.png) shows all 4 investor bars overlapping at
# each date from the SAME zero baseline (not grouped side-by-side, not
# stacked end-to-end). This is achieved by binding each dataset to its own
# (hidden) x-axis so Chart.js places every bar at the same category
# position.

def test_fluxo_chart_datasets_have_distinct_xaxis_ids(monkeypatch):
    """Each of the 4 datasets is bound to its own x-axis (x/x2/x3/x4) so
    bars overlap at the same category position instead of grouping."""
    chart = _get_fluxo_chart(monkeypatch)
    datasets = chart["chart_data"]["data"]["datasets"]
    axis_ids = [d.get("xAxisID") for d in datasets]
    assert axis_ids == ["x", "x2", "x3", "x4"]


def test_fluxo_chart_has_4_x_axes(monkeypatch):
    """Scales include x (displayed) + x2/x3/x4 (hidden) for overlapping."""
    chart = _get_fluxo_chart(monkeypatch)
    scales = chart["chart_data"]["options"]["scales"]
    assert "x" in scales
    assert "x2" in scales
    assert "x3" in scales
    assert "x4" in scales


def test_fluxo_chart_only_x_axis_displayed(monkeypatch):
    """Only the primary x-axis is displayed; x2/x3/x4 are hidden."""
    chart = _get_fluxo_chart(monkeypatch)
    scales = chart["chart_data"]["options"]["scales"]
    assert scales["x"].get("display") is True
    assert scales["x2"].get("display") is False
    assert scales["x3"].get("display") is False
    assert scales["x4"].get("display") is False


def test_fluxo_chart_axes_not_stacked(monkeypatch):
    """Axes are NOT stacked (overlapping, not end-to-end stacking)."""
    chart = _get_fluxo_chart(monkeypatch)
    scales = chart["chart_data"]["options"]["scales"]
    assert scales["x"].get("stacked") is False
    assert scales["y"].get("stacked") is False


def test_fluxo_chart_hidden_axes_inherit_labels(monkeypatch):
    """Hidden x2/x3/x4 have no explicit 'labels' so they inherit
    chart.data.labels (keeps the range selector working — it only
    updates chart.data.labels, not per-scale labels)."""
    chart = _get_fluxo_chart(monkeypatch)
    scales = chart["chart_data"]["options"]["scales"]
    for ax in ("x2", "x3", "x4"):
        assert "labels" not in scales[ax], (
            f"{ax} must not define its own labels (inherit chart.data.labels)")


def test_fluxo_chart_bar_sizing_identical_across_axes(monkeypatch):
    """barPercentage + categoryPercentage are identical on all 4 axes so
    bars fully overlap (same width, same position)."""
    chart = _get_fluxo_chart(monkeypatch)
    scales = chart["chart_data"]["options"]["scales"]
    ref = (scales["x"].get("barPercentage"), scales["x"].get("categoryPercentage"))
    for ax in ("x2", "x3", "x4"):
        assert (scales[ax].get("barPercentage"),
                scales[ax].get("categoryPercentage")) == ref


# ────────────────────────────────────────────────────────────────────────
# [v3] Negative value cells render in red (tables)
# ────────────────────────────────────────────────────────────────────────
# The shared table template detects negatives via cell_text.startswith('-'),
# but format_brl produces "R$ -1.582,35 mi" (starts with "R$ "), so the
# template's own detection misses them. report.py now sets cell["color"]
# explicitly for negatives, which the template applies via its cell_color
# branch.

_NEG = "#ef4444"


def test_fluxo_table_negative_cell_has_red_color(monkeypatch):
    """Negative value cells carry cell["color"] = red.

    Mock row 0 (2026-08-17): estrangeiro = -496.07 (negative)."""
    table = _get_fluxo_table(monkeypatch)
    first_row = table["rows"][0]
    estrangeiro_cell = first_row[1]  # col 1 = Estrangeiro
    assert estrangeiro_cell["color"] == _NEG


def test_fluxo_table_positive_cell_has_no_color(monkeypatch):
    """Positive value cells do NOT carry cell["color"] (render in default).

    Mock row 0 (2026-08-17): institucional = 71.25 (positive)."""
    table = _get_fluxo_table(monkeypatch)
    first_row = table["rows"][0]
    institucional_cell = first_row[2]  # col 2 = Institucional
    assert "color" not in institucional_cell


def test_fluxo_table_mixed_sign_row_colors(monkeypatch):
    """Row with mixed signs: negatives get red, positives don't.

    Mock row 1 (2026-08-18): estrangeiro=-1782.10 (neg), institucional=
    1362.50 (pos), inst_financeira=-9.69 (neg)."""
    table = _get_fluxo_table(monkeypatch)
    row = table["rows"][1]
    assert row[1]["color"] == _NEG              # estrangeiro negative
    assert "color" not in row[2]               # institucional positive
    assert row[4]["color"] == _NEG              # inst_financeira negative


def test_investor_table_negative_cells_have_red_color(monkeypatch):
    """Per-investor Diario table: all negative value cells are red.

    Estrangeiro mock values are all negative (-496.07, -1782.10, -1582.35)."""
    table = _get_investor_table(monkeypatch, "Estrangeiro", "Diario")
    for row in table["rows"]:
        value_cell = row[1]
        assert value_cell["color"] == _NEG, (
            f"Expected red for negative value, got cell={value_cell}")


# ────────────────────────────────────────────────────────────────────────
# [v3] Line segment red-when-negative (Mensal + Anual)
# ────────────────────────────────────────────────────────────────────────
# The reference charts (Mensal.png, Anual.png) show the line SEGMENT
# turning red when below zero. Chart.js needs a `segment.borderColor`
# function for this, but the template's JSON clone strips functions. So
# report.py sets the `_segment_negative_red` flag, and the dashboard
# template injects the real callback post-clone.

def _get_monthly_chart(monkeypatch, investor_label: str = "Estrangeiro") -> dict:
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    tab = next(t for t in res["tabs"] if t["name"] == investor_label)
    subtabs = next(s for s in tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    monthly = next(t for t in subtabs if t["name"] == "Mensal")
    return next(s for s in monthly["sections"] if s.get("type") == "chart")


def _get_annual_chart(monkeypatch, investor_label: str = "Estrangeiro") -> dict:
    _patch_query(monkeypatch)
    from skills.ddm.fluxo.modes import dashboard
    res = dashboard.dashboard()
    tab = next(t for t in res["tabs"] if t["name"] == investor_label)
    subtabs = next(s for s in tab["sections"]
                   if s.get("type") == "subtabs")["tabs"]
    annual = next(t for t in subtabs if t["name"] == "Anual")
    return next(s for s in annual["sections"] if s.get("type") == "chart")


def test_monthly_chart_has_segment_negative_red_flag(monkeypatch):
    """Monthly chart options carry the _segment_negative_red flag (consumed
    by the dashboard template to inject the segment.borderColor callback)."""
    chart = _get_monthly_chart(monkeypatch)
    opts = chart["chart_data"]["options"]
    assert opts.get("_segment_negative_red") is True


def test_monthly_chart_segment_colors_use_template_defaults(monkeypatch):
    """Monthly chart does NOT override segment colors — uses template defaults.

    [v5] The _segment_pos_color / _segment_neg_color / _segment_cross_color
    overrides were removed from report.py. The template's _applySegmentColors
    function has its own defaults (#22c55e / #ef4444 / #eab308) that match.
    Only the _segment_negative_red flag is set (to opt into segment coloring).
    """
    chart = _get_monthly_chart(monkeypatch)
    opts = chart["chart_data"]["options"]
    assert opts.get("_segment_negative_red") is True
    # The explicit color overrides should NOT be present (template defaults).
    assert "_segment_pos_color" not in opts
    assert "_segment_neg_color" not in opts
    assert "_segment_cross_color" not in opts


def test_monthly_chart_has_per_point_colors(monkeypatch):
    """Monthly chart points are colored per-sign (green/red) for
    consistency with the segment-colored line."""
    chart = _get_monthly_chart(monkeypatch)
    ds = chart["chart_data"]["data"]["datasets"][0]
    points = ds["pointBackgroundColor"]
    assert isinstance(points, list)
    assert len(points) == 1  # 1 mock month
    # Mock month Ago/2026 value = -3860.52 (negative) → red point.
    assert points[0] == "#ef4444"


def test_annual_chart_has_segment_negative_red_flag(monkeypatch):
    """Annual chart options carry the _segment_negative_red flag."""
    chart = _get_annual_chart(monkeypatch)
    opts = chart["chart_data"]["options"]
    assert opts.get("_segment_negative_red") is True


def test_annual_chart_segment_colors_use_template_defaults(monkeypatch):
    """Annual chart does NOT override segment colors — uses template defaults.

    [v5] Same as monthly: the _segment_*_color overrides were removed.
    Only _segment_negative_red=True is set (template handles the rest).
    """
    chart = _get_annual_chart(monkeypatch)
    opts = chart["chart_data"]["options"]
    assert opts.get("_segment_negative_red") is True
    assert "_segment_pos_color" not in opts
    assert "_segment_neg_color" not in opts
    assert "_segment_cross_color" not in opts


def test_annual_chart_has_per_point_colors(monkeypatch):
    """Annual chart points are colored per-sign (green/red)."""
    chart = _get_annual_chart(monkeypatch)
    ds = chart["chart_data"]["data"]["datasets"][0]
    points = ds["pointBackgroundColor"]
    assert isinstance(points, list)
    assert len(points) == 3  # 3 mock days
    # Mock annual cumulative for Estrangeiro: -496.07, -2278.17, -3860.52
    # (all negative → all red points).
    assert all(c == "#ef4444" for c in points)


# ────────────────────────────────────────────────────────────────────────
# [v4] Range selector: DD/MM/YYYY label parsing (dashboard.html template)
# ────────────────────────────────────────────────────────────────────────
# The Fluxo/Diario/Anual charts use DD/MM/YYYY labels. The template's
# labelToISO must parse these to YYYY-MM-DD for the range selector cutoff
# comparison; otherwise "19/08/2026" >= "2025-08-23" fails lexicographically
# ("1" < "2") and sub-10A ranges filter out almost every label.

def test_dashboard_template_parses_dd_mm_yyyy_labels():
    """The dashboard.html template's labelToISO handles DD/MM/YYYY.

    Reads the actual template file (not the generated HTML) to ensure
    the regex is present at the source.
    """
    from pathlib import Path
    tpl = Path(__file__).resolve().parents[4] / "tools" / "report_ops" / "templates" / "dashboard.html"
    content = tpl.read_text(encoding="utf-8")
    # DD/MM/YYYY regex must be present (with capturing groups + escapes).
    assert r"\d{2})\/(\d{2})\/(\d{4}" in content, (
        "DD/MM/YYYY regex missing from dashboard.html labelToISO")
    # The conversion must reorder to YYYY-MM-DD (group 3 - 2 - 1).
    assert "d[3] + '-' + d[2] + '-' + d[1]" in content, (
        "DD/MM/YYYY -> YYYY-MM-DD reordering missing")


def test_dashboard_template_has_3color_segment_logic():
    """The _applySegmentColors function implements the 3-color rule:
    pos→pos=green, neg→neg=red, crossing=yellow."""
    from pathlib import Path
    tpl = Path(__file__).resolve().parents[4] / "tools" / "report_ops" / "templates" / "dashboard.html"
    content = tpl.read_text(encoding="utf-8")
    assert "_segment_cross_color" in content, (
        "_segment_cross_color missing from _applySegmentColors")
    assert "y0 >= 0 && y1 >= 0" in content, (
        "pos→pos green branch missing")
    assert "y0 < 0 && y1 < 0" in content, (
        "neg→neg red branch missing")
    assert "return crossColor" in content, (
        "crossing yellow branch missing")


def test_dashboard_template_segment_colors_called_in_render():
    """_applySegmentColors is called in _renderChart (not just defined)."""
    from pathlib import Path
    tpl = Path(__file__).resolve().parents[4] / "tools" / "report_ops" / "templates" / "dashboard.html"
    content = tpl.read_text(encoding="utf-8")
    # Must be called right after _applyTooltipPercent in the render path.
    assert "_applySegmentColors(config)" in content, (
        "_applySegmentColors(config) call missing from _renderChart")

