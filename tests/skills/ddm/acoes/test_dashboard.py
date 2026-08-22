"""tests/skills/ddm/acoes/test_dashboard.py - dashboard tests with mocked query_engine.

Mocks data_sources.ddm.acoes.query_engine.stocks_list + summary so no DB /
HTTP access is needed. Verifies:
  - 1 tab total: Acoes (group: Acoes)
  - Tab field is "name" (not "label")
  - KPIs are at top level (not per-tab)
  - Table section is sortable: sortable=True + default_sort = {column: 2, direction: "desc"}
    + sort_types = ["text","text","number","number","number"]
  - Numeric cells are dicts with text + data-value attributes
  - Variation cells with negative values would be red (negative_red=True)
  - Distribution chart present + uses 16 colored bars (one per price range)
  - Distribution chart bar colors match skills._price_colors palette
"""
from __future__ import annotations


_MOCK_STOCKS = [
    {"ticker": "PETR4", "name": "Petrobras", "negocios": 52792400,
     "last_price": 44.30, "variation": 2.78, "ref_date": "2025-01-15",
     "synced_at": "2025-01-15T12:00:00+00:00"},
    {"ticker": "VALE3", "name": "Vale", "negocios": 38412100,
     "last_price": 61.45, "variation": -1.32, "ref_date": "2025-01-15",
     "synced_at": "2025-01-15T12:00:00+00:00"},
    {"ticker": "ITUB4", "name": "Itau Unibanco", "negocios": 25100500,
     "last_price": 33.20, "variation": 0.45, "ref_date": "2025-01-15",
     "synced_at": "2025-01-15T12:00:00+00:00"},
]


_MOCK_SUMMARY = {
    "status": "ok", "total": 3, "ref_date": "2025-01-15",
    "most_traded":    {"ticker": "PETR4", "name": "Petrobras", "negocios": 52792400},
    "biggest_gainer": {"ticker": "PETR4", "name": "Petrobras", "variation": 2.78},
    "biggest_loser":  {"ticker": "VALE3", "name": "Vale",       "variation": -1.32},
}


def _mock_stocks_list(order_by="negocios", direction="desc", limit=0):
    return {
        "status": "ok", "count": len(_MOCK_STOCKS),
        "stocks": list(_MOCK_STOCKS),
    }


def _mock_summary():
    return dict(_MOCK_SUMMARY)


def _patch_query(monkeypatch):
    """Patch query_engine functions at the source module + the dashboard
    namespace (local refs bound at import time)."""
    import data_sources.ddm.acoes.query_engine as qe
    monkeypatch.setattr(qe, "stocks_list", _mock_stocks_list)
    monkeypatch.setattr(qe, "summary", _mock_summary)

    from skills.ddm.acoes.modes import dashboard
    monkeypatch.setattr(dashboard, "stocks_list", _mock_stocks_list)
    monkeypatch.setattr(dashboard, "summary", _mock_summary)


def test_dashboard_has_1_tab(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    assert res["status"] == "ok"
    tab_names = [t["name"] for t in res["tabs"]]
    assert tab_names == ["Acoes"]


def test_dashboard_tab_group_is_acoes(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    assert res["tabs"][0]["group"] == "Acoes"


def test_dashboard_uses_name_not_label(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    for t in res["tabs"]:
        assert "name" in t
        assert "label" not in t


def test_dashboard_kpis_at_top_level(monkeypatch):
    """KPIs are at top level (not per-tab)."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    assert "kpis" in res
    # 4 KPIs: total, most traded, biggest gainer, biggest loser.
    assert len(res["kpis"]) == 4
    for t in res["tabs"]:
        assert "kpis" not in t
        assert "_kpis" not in t


def test_dashboard_kpis_have_expected_labels(monkeypatch):
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    labels = [k["label"] for k in res["kpis"]]
    assert "Total de Acoes" in labels
    assert "Mais Negociada" in labels
    assert "Maior Alta" in labels
    assert "Maior Baixa" in labels


def test_dashboard_table_is_sortable(monkeypatch):
    """The stocks table section has sortable=True + default_sort set +
    sort_types set."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    table_secs = [s for s in res["tabs"][0]["sections"] if s.get("type") == "table"]
    assert len(table_secs) == 1
    ts = table_secs[0]
    assert ts.get("sortable") is True
    assert ts.get("default_sort") == {"column": 2, "direction": "desc"}
    # sort_types: text | text | number | number | number (Ticker + Nome are
    # text; Negocios + Ultima + Variacao are numeric).
    assert ts.get("sort_types") == ["text", "text", "number", "number", "number"]


def test_dashboard_table_has_column_align(monkeypatch):
    """Table has column_align: left | left | right | right | right."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    ts = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "table")
    assert ts["column_align"] == ["left", "left", "right", "right", "right"]


def test_dashboard_table_has_negative_red(monkeypatch):
    """Negative variation values render in red (negative_red=True)."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    ts = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "table")
    assert ts.get("negative_red") is True


def test_dashboard_table_columns(monkeypatch):
    """Table has the 5 expected columns."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    ts = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "table")
    assert ts["columns"] == ["Ticker", "Nome", "Negocios",
                             "Ultima (R$)", "Variacao"]


def test_dashboard_numeric_cells_have_data_value(monkeypatch):
    """Numeric cells are dicts with text + data-value attributes."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    ts = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "table")
    # First row: PETR4 | Petrobras | negocios_cell | price_cell | variation_cell
    first_row = ts["rows"][0]
    # Ticker + name are plain strings.
    assert first_row[0] == "PETR4"
    assert first_row[1] == "Petrobras"
    # Numeric cells are dicts with text + data-value.
    negocios_cell = first_row[2]
    assert isinstance(negocios_cell, dict)
    assert "text" in negocios_cell
    assert "data-value" in negocios_cell
    assert negocios_cell["data-value"] == "52792400"
    price_cell = first_row[3]
    assert isinstance(price_cell, dict)
    assert price_cell["data-value"] == "44.300000"
    var_cell = first_row[4]
    assert isinstance(var_cell, dict)
    assert var_cell["data-value"] == "2.780000"


def test_dashboard_variation_cell_text_has_sign(monkeypatch):
    """Variation cell text is formatted with sign + PT-BR comma decimal + %."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    ts = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "table")
    petr4_var = ts["rows"][0][4]
    vale3_var = ts["rows"][1][4]
    assert petr4_var["text"] == "+2,78%"
    assert vale3_var["text"] == "-1,32%"


# ────────────────────────────────────────────────────────────────────────
# Distribution chart tests
# ────────────────────────────────────────────────────────────────────────

def test_dashboard_has_distribution_chart(monkeypatch):
    """Dashboard emits a price-distribution chart (Chart.js bar)."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    chart_secs = [s for s in res["tabs"][0]["sections"] if s.get("type") == "chart"]
    assert len(chart_secs) == 1
    cs = chart_secs[0]
    assert cs["title"] == "Distribuicao de Precos"
    assert cs["chart_data"]["type"] == "bar"
    # 1 dataset (single bar series).
    assert len(cs["chart_data"]["data"]["datasets"]) == 1


def test_distribution_chart_has_16_bars(monkeypatch):
    """Distribution chart has 16 bars (one per price-range bucket)."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    cs = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "chart")
    labels = cs["chart_data"]["data"]["labels"]
    counts = cs["chart_data"]["data"]["datasets"][0]["data"]
    bg_colors = cs["chart_data"]["data"]["datasets"][0]["backgroundColor"]
    assert len(labels) == 16
    assert len(counts) == 16
    assert len(bg_colors) == 16


def test_distribution_chart_counts_match_input(monkeypatch):
    """The 3 mock stocks (44.30, 61.45, 33.20) should each fall in their
    respective price-range buckets:
      - 33.20 -> '30 <= X < 40'
      - 44.30 -> '40 <= X < 50'
      - 61.45 -> '60 <= X < 70'
    Total non-zero counts should be 3 (one per bucket).
    """
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    cs = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "chart")
    labels = cs["chart_data"]["data"]["labels"]
    counts = cs["chart_data"]["data"]["datasets"][0]["data"]
    by_label = dict(zip(labels, counts))
    # 3 mock stocks -> 3 non-zero buckets.
    assert sum(counts) == 3
    assert by_label["30 \u2264 X < 40"] == 1   # ITUB4 @ 33.20
    assert by_label["40 \u2264 X < 50"] == 1   # PETR4 @ 44.30
    assert by_label["60 \u2264 X < 70"] == 1   # VALE3 @ 61.45


def test_distribution_chart_bar_colors_match_price_palette(monkeypatch):
    """Bar colors match skills/_price_colors.ALL_RANGES palette exactly."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    from skills._price_colors import ALL_RANGES
    res = dashboard.dashboard()
    cs = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "chart")
    bg_colors = cs["chart_data"]["data"]["datasets"][0]["backgroundColor"]
    palette = [bg for (_label, bg, _tc) in ALL_RANGES]
    assert bg_colors == palette


def test_distribution_chart_title(monkeypatch):
    """Chart title + section title are 'Distribuicao de Precos'."""
    _patch_query(monkeypatch)
    from skills.ddm.acoes.modes import dashboard
    res = dashboard.dashboard()
    cs = next(s for s in res["tabs"][0]["sections"] if s.get("type") == "chart")
    assert cs["title"] == "Distribuicao de Precos"
    assert cs["chart_data"]["options"]["plugins"]["title"]["text"] == "Distribuicao de Precos"
