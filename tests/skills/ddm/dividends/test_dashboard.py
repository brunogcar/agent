"""tests/skills/ddm/dividends/test_dashboard.py - dashboard tests with mocked query_engine.

Mocks data_sources.ddm.dividends.query_engine.dividends_list + summary so no
DB / HTTP access is needed. Verifies:
  - 1 tab total: Dividendos
  - 4 KPIs at top level (total dividendos, valor total, maior dividendo,
    proximo pagamento)
  - Distribution chart section (grouped bar: Dividendo vs JCP, 8 buckets)
  - Sortable dividends table section (sortable=True + sort_types +
    default_sort + column_align + correct columns)
  - Date cells displayed as DD/MM/YYYY (PT-BR)
  - Numeric Valor cells are dicts {"text", "data-value", "bg", "color"} for
    sortable data + DPA-range coloring (skills/_colors/dpa.py)
  - NO table-level negative_red / price_colors / cell_colors keys (per-cell
    bg/color is applied to Valor via dpa_range_color)
"""
from __future__ import annotations


_MOCK_DIVIDENDS = [
    {"ticker": "BBDC3", "tipo": "Dividendo", "value": 0.017250,
     "record_date": "2026-07-01", "ex_date": "2026-07-02",
     "payment_date": "2026-08-03"},
    {"ticker": "PETR4", "tipo": "JCP", "value": 7.96,
     "record_date": "2026-06-15", "ex_date": "2026-06-16",
     "payment_date": "2026-07-30"},
    {"ticker": "VALE3", "tipo": "Dividendo", "value": 0.006,
     "record_date": "2026-12-10", "ex_date": "2026-12-11",
     "payment_date": "2027-01-15"},
    {"ticker": "ITUB4", "tipo": "Dividendo", "value": 0.50,
     "record_date": "2026-03-05", "ex_date": "2026-03-06",
     "payment_date": "2026-04-10"},
    {"ticker": "ABEV3", "tipo": "JCP", "value": 0.12,
     "record_date": "2026-08-01", "ex_date": "2026-08-02",
     "payment_date": "2026-09-05"},
]


_MOCK_SUMMARY = {
    "status": "ok",
    "total_dividends": 5,
    "total_value": 8.603250,
    "biggest": {
        "ticker": "PETR4", "tipo": "JCP", "value": 7.96,
        "record_date": "2026-06-15",
    },
    "next_payment_date": "2026-04-10",
    "by_tipo": {"Dividendo": 3, "JCP": 2},
}


def _mock_dividends_list(order_by="value", direction="desc", limit=0):
    rows = list(_MOCK_DIVIDENDS)
    # Apply the requested sort (mirror what the DB would do) so the test
    # reflects real behavior.
    reverse = (direction == "desc")
    if order_by == "value":
        rows.sort(key=lambda r: r["value"], reverse=reverse)
    elif order_by == "ticker":
        rows.sort(key=lambda r: r["ticker"], reverse=reverse)
    elif order_by in ("record_date", "ex_date", "payment_date"):
        rows.sort(key=lambda r: r[order_by] or "", reverse=reverse)
    elif order_by == "tipo":
        rows.sort(key=lambda r: r["tipo"] or "", reverse=reverse)
    return {
        "status": "ok", "count": len(rows),
        "order_by": order_by, "direction": direction,
        "dividends": rows,
    }


def _mock_summary():
    return dict(_MOCK_SUMMARY)


def _patch_query(monkeypatch):
    """Patch query_engine functions at the source module + the dashboard
    namespace (local refs bound at import time)."""
    import data_sources.ddm.dividends.query_engine as qe
    monkeypatch.setattr(qe, "dividends_list", _mock_dividends_list)
    monkeypatch.setattr(qe, "summary", _mock_summary)

    from skills.ddm.dividends.modes import dashboard
    monkeypatch.setattr(dashboard, "dividends_list", _mock_dividends_list)
    monkeypatch.setattr(dashboard, "summary", _mock_summary)


# ────────────────────────────────────────────────────────────────────────
# Dashboard structure tests
# ────────────────────────────────────────────────────────────────────────

def test_dashboard_has_1_tab(monkeypatch):
    """Dashboard has exactly 1 tab: Dividendos."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    assert res["status"] == "ok"
    tab_names = [t["name"] for t in res["tabs"]]
    assert tab_names == ["Dividendos"]


def test_dashboard_tab_group_is_dividendos(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    assert res["tabs"][0]["group"] == "Dividendos"


def test_dashboard_kpis_at_top_level(monkeypatch):
    """4 KPIs are at top level (not per-tab)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    assert "kpis" in res
    assert len(res["kpis"]) == 4
    for t in res["tabs"]:
        assert "kpis" not in t
        assert "_kpis" not in t


def test_dashboard_kpi_labels(monkeypatch):
    """KPI labels are PT-BR + match the spec."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    labels = [k["label"] for k in res["kpis"]]
    assert labels == [
        "Total de dividendos",
        "Valor total",
        "Maior dividendo",
        "Proximo pagamento",
    ]


def test_dashboard_kpi_total_dividends_formatted_as_int(monkeypatch):
    """The total-dividendos KPI value is formatted as a PT-BR integer
    ('5', not '5.0' or '5,00')."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    kpi = res["kpis"][0]
    assert kpi["value"] == "5"
    assert "Dividendo: 3" in kpi["subtitle"]
    assert "JCP: 2" in kpi["subtitle"]


def test_dashboard_kpi_valor_total_formatted_as_brl(monkeypatch):
    """The valor-total KPI is formatted as R$ x,xx (>= 1.0 -> 2 decimals)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    kpi = res["kpis"][1]
    # 8.603250 >= 1.0 -> 2 decimals.
    assert kpi["value"] == "R$ 8,60"


def test_dashboard_kpi_maior_dividendo(monkeypatch):
    """The maior-dividendo KPI shows PETR4 + R$ 7,96 in the subtitle."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    kpi = res["kpis"][2]
    assert kpi["value"] == "R$ 7,96"
    assert "PETR4" in kpi["subtitle"]
    assert "R$ 7,96" in kpi["subtitle"]


def test_dashboard_kpi_proximo_pagamento_formatted_as_ptbr_date(monkeypatch):
    """The proximo-pagamento KPI displays the date as DD/MM/YYYY."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    kpi = res["kpis"][3]
    assert kpi["value"] == "10/04/2026"


# ────────────────────────────────────────────────────────────────────────
# Distribution chart tests
# ────────────────────────────────────────────────────────────────────────

def test_dashboard_has_distribution_chart(monkeypatch):
    """The Dividendos tab contains a chart section (the distribution chart)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tab = res["tabs"][0]
    charts = [s for s in tab["sections"] if s.get("type") == "chart"]
    assert len(charts) == 1
    assert "Distribuicao" in charts[0]["title"]


def test_distribution_chart_is_grouped_bar(monkeypatch):
    """The distribution chart is a bar chart with 2 datasets (Dividendo +
    JCP), NOT stacked (grouped side-by-side)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    chart = next(s for s in res["tabs"][0]["sections"]
                 if s.get("type") == "chart")
    assert chart["chart_data"]["type"] == "bar"
    datasets = chart["chart_data"]["data"]["datasets"]
    assert len(datasets) == 2
    labels = [d["label"] for d in datasets]
    assert "Dividendo" in labels
    assert "JCP" in labels


def test_distribution_chart_has_8_buckets(monkeypatch):
    """The X-axis has 8 value-range buckets."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    chart = next(s for s in res["tabs"][0]["sections"]
                 if s.get("type") == "chart")
    labels = chart["chart_data"]["data"]["labels"]
    assert len(labels) == 8
    assert labels[0] == "<0,05"
    assert labels[-1] == ">=5,00"


def test_distribution_chart_bucket_counts(monkeypatch):
    """Each dividend is counted into the right bucket + tipo.

    Mock data:
      BBDC3  Dividendo  0.017250  -> bucket 0 (<0,05)   Dividendo
      PETR4  JCP        7.96      -> bucket 7 (>=5,00)  JCP
      VALE3  Dividendo  0.006     -> bucket 0 (<0,05)   Dividendo
      ITUB4  Dividendo  0.50      -> bucket 3 (0,25-0,50) Dividendo
      ABEV3  JCP        0.12      -> bucket 2 (0,10-0,25) JCP
    """
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    chart = next(s for s in res["tabs"][0]["sections"]
                 if s.get("type") == "chart")
    datasets = {d["label"]: d["data"] for d in chart["chart_data"]["data"]["datasets"]}
    dividendo = datasets["Dividendo"]
    jcp = datasets["JCP"]
    # bucket 0 (<0,05): BBDC3 + VALE3 -> 2 Dividendo, 0 JCP
    assert dividendo[0] == 2
    assert jcp[0] == 0
    # bucket 2 (0,10-0,25): ABEV3 -> 0 Dividendo, 1 JCP
    assert dividendo[2] == 0
    assert jcp[2] == 1
    # bucket 4 (0,50-1,00): ITUB4 (value=0.50) -> 1 Dividendo, 0 JCP
    assert dividendo[4] == 1
    assert jcp[4] == 0
    # bucket 7 (>=5,00): PETR4 -> 0 Dividendo, 1 JCP
    assert dividendo[7] == 0
    assert jcp[7] == 1


def test_distribution_chart_colors_match_spec(monkeypatch):
    """Dividendo = teal #0d9488, JCP = amber #f59e0b."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    chart = next(s for s in res["tabs"][0]["sections"]
                 if s.get("type") == "chart")
    for ds in chart["chart_data"]["data"]["datasets"]:
        if ds["label"] == "Dividendo":
            assert ds["backgroundColor"] == "#0d9488"
        elif ds["label"] == "JCP":
            assert ds["backgroundColor"] == "#f59e0b"


# ────────────────────────────────────────────────────────────────────────
# Sortable dividends table tests
# ────────────────────────────────────────────────────────────────────────

def test_dashboard_has_sortable_dividends_table(monkeypatch):
    """The Dividendos tab contains a table section with sortable=True."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tab = res["tabs"][0]
    tables = [s for s in tab["sections"] if s.get("type") == "table"]
    assert len(tables) == 1
    assert tables[0].get("sortable") is True


def test_dividends_table_has_6_columns(monkeypatch):
    """Columns: Codigo | Tipo | Valor (R$) | Registro | Ex | Pagamento."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    assert tables[0]["columns"] == [
        "Codigo", "Tipo", "Valor (R$)",
        "Registro", "Ex", "Pagamento",
    ]


def test_dividends_table_column_align(monkeypatch):
    """column_align: left, left, right, right, right, right."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    assert tables[0]["column_align"] == [
        "left", "left", "right", "right", "right", "right",
    ]


def test_dividends_table_sort_types(monkeypatch):
    """sort_types: text, text, number, text, text, text (Valor is the only
    numeric column)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    assert tables[0]["sort_types"] == [
        "text", "text", "number", "text", "text", "text",
    ]


def test_dividends_table_default_sort_is_value_desc(monkeypatch):
    """default_sort: {column: 2 (Valor), direction: 'desc'}."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    assert tables[0]["default_sort"] == {"column": 2, "direction": "desc"}


def test_dividends_table_no_table_level_color_keys(monkeypatch):
    """The dividends table MUST NOT carry negative_red or table-level color
    metadata (price_colors / cell_colors). Per-cell bg/color on Valor comes
    from dpa_range_color (skills/_colors/dpa.py) and is applied directly to
    each Valor cell dict, not as a bulk table attribute.
    """
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    tbl = tables[0]
    assert "negative_red" not in tbl or tbl["negative_red"] is False
    assert "price_colors" not in tbl
    assert "cell_colors" not in tbl


def test_dividends_table_dates_displayed_as_ptbr(monkeypatch):
    """Date cells display as DD/MM/YYYY (PT-BR), NOT YYYY-MM-DD."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    rows = tables[0]["rows"]
    # Find the BBDC3 row.
    bbdc3 = next(r for r in rows if r[0] == "BBDC3")
    # cols: 0=Codigo, 1=Tipo, 2=Valor, 3=Registro, 4=Ex, 5=Pagamento
    assert bbdc3[3] == "01/07/2026"  # Registro (PT-BR)
    assert bbdc3[4] == "02/07/2026"  # Ex (PT-BR)
    assert bbdc3[5] == "03/08/2026"  # Pagamento (PT-BR)


def test_dividends_table_numeric_cell_is_dict_with_data_value(monkeypatch):
    """Each Valor cell is a dict {"text": "R$ 0,017250", "data-value": "0.017250",
    "bg": "#fff3d6", "color": "#000"} so the sortable macro can emit
    <td data-value="0.017250" style="background:#fff3d6;color:#000">R$ 0,017250</td>.
    The bg + color come from dpa_range_color (skills/_colors/dpa.py)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    rows = tables[0]["rows"]
    bbdc3 = next(r for r in rows if r[0] == "BBDC3")
    valor_cell = bbdc3[2]
    assert isinstance(valor_cell, dict)
    # Cell shape: text + data-value + bg + color (DPA range coloring).
    assert set(valor_cell.keys()) == {"text", "data-value", "bg", "color"}
    assert valor_cell["text"] == "R$ 0,017250"
    # data_value should be a parseable float string.
    assert float(valor_cell["data-value"]) == 0.017250
    # BBDC3 value=0.017250 -> "0 < X <= 0.15" -> bg=#fff3d6, color=#000.
    assert valor_cell["bg"] == "#fff3d6"
    assert valor_cell["color"] == "#000"


def test_dividends_table_dpa_colors_match_value_range(monkeypatch):
    """Each Valor cell's bg + color come from skills/_colors/dpa.dpa_range_color.

    Mock data + expected DPA range:
      BBDC3  value=0.017250 -> "0 < X <= 0.15"  -> #fff3d6 / #000
      PETR4  value=7.96     -> "X > 7.0"        -> #1a3a8a / #fff
      VALE3  value=0.006    -> "0 < X <= 0.15"  -> #fff3d6 / #000
      ITUB4  value=0.50     -> "0.30 < X <= 1.0" -> #deebf7 / #000
      ABEV3  value=0.12     -> "0 < X <= 0.15"  -> #fff3d6 / #000
    """
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    from skills._colors.dpa import dpa_range_color
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    rows = tables[0]["rows"]
    by_ticker = {r[0]: r for r in rows}
    for ticker, expected_value in [
        ("BBDC3", 0.017250),
        ("PETR4", 7.96),
        ("VALE3", 0.006),
        ("ITUB4", 0.50),
        ("ABEV3", 0.12),
    ]:
        row = by_ticker[ticker]
        valor_cell = row[2]
        expected = dpa_range_color(expected_value)
        assert valor_cell["bg"] == expected["bg"], (
            f"{ticker} value={expected_value}: expected bg={expected['bg']}, "
            f"got bg={valor_cell['bg']}")
        assert valor_cell["color"] == expected["color"], (
            f"{ticker} value={expected_value}: expected color={expected['color']}, "
            f"got color={valor_cell['color']}")


def test_dividends_table_small_value_uses_6_decimals(monkeypatch):
    """Values < 1.0 are formatted with 6 decimals (R$ 0,017250)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    rows = tables[0]["rows"]
    bbdc3 = next(r for r in rows if r[0] == "BBDC3")
    assert bbdc3[2]["text"] == "R$ 0,017250"


def test_dividends_table_large_value_uses_2_decimals(monkeypatch):
    """Values >= 1.0 are formatted with 2 decimals (R$ 7,96)."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    rows = tables[0]["rows"]
    petr4 = next(r for r in rows if r[0] == "PETR4")
    assert petr4[2]["text"] == "R$ 7,96"
    assert float(petr4[2]["data-value"]) == 7.96


def test_dividends_table_ticker_is_plain_string_tipo_is_colored_dict(monkeypatch):
    """Ticker (col 0) is plain string, Tipo (col 1) is colored dict."""
    _patch_query(monkeypatch)
    from skills.ddm.dividends.modes import dashboard
    res = dashboard.dashboard()
    tables = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    rows = tables[0]["rows"]
    bbdc3 = next(r for r in rows if r[0] == "BBDC3")
    assert isinstance(bbdc3[0], str)
    assert bbdc3[0] == "BBDC3"
    assert isinstance(bbdc3[1], dict)  # tipo is now a colored dict
    assert bbdc3[1]["text"] == "Dividendo"
    assert bbdc3[1]["color"] == "#0d9488"  # teal for Dividendo


# ────────────────────────────────────────────────────────────────────────
# Error-path tests
# ────────────────────────────────────────────────────────────────────────

def test_dashboard_handles_no_data_gracefully(monkeypatch):
    """When dividends_list returns not_synced, the dashboard still returns
    status=ok with an error section in the tab."""
    def _mock_empty(order_by="value", direction="desc", limit=0):
        return {"status": "not_synced", "error": "DB not found"}
    def _mock_empty_summary():
        return {"status": "not_synced", "error": "DB not found"}

    import data_sources.ddm.dividends.query_engine as qe
    monkeypatch.setattr(qe, "dividends_list", _mock_empty)
    monkeypatch.setattr(qe, "summary", _mock_empty_summary)

    from skills.ddm.dividends.modes import dashboard
    monkeypatch.setattr(dashboard, "dividends_list", _mock_empty)
    monkeypatch.setattr(dashboard, "summary", _mock_empty_summary)

    res = dashboard.dashboard()
    assert res["status"] == "ok"
    # Tab still exists.
    assert len(res["tabs"]) == 1
    # KPIs still rendered (with "-" values).
    assert len(res["kpis"]) == 4
    # Errors surfaced at top level.
    assert len(res["errors"]) >= 1
