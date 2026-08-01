"""Tests for skills/cvm/insider/ — dashboard mode.

[v1.1] Split out of the original single-file `test_insider.py`.
Covers the dashboard mode (multi-tab composition that orchestrates the
underlying history + by_role + summary modes):

  - no company -> short-circuit error
  - basic shape (status, tabs, kpis lists)
  - tab names exactly ['Overview', 'Recent Transactions', 'By Role',
    'Monthly Net']
  - top-level KPI cards (Sentimento, Volume Comprado, Volume Vendido,
    Net Volume)
  - degradation when summary()/history()/by_role() all fail (4 tabs +
    all KPIs as '—')
  - route dispatches to dashboard mode

The mock VLMO setup mirrors `test_insider.py` (duplicated here so this
test module is self-contained).
"""
from __future__ import annotations

from skills.cvm.insider import MANIFEST, route
from skills.cvm.insider.modes.dashboard import dashboard


# ── Synthetic data (mirror test_insider.py) ──────────────────────────────────

MOCK_HISTORY = {
    "status": "ok", "company": "PETR4", "cnpj": "33000167000101", "count": 2,
    "movements": [
        {"Data_Movimentacao": "2026-07-15", "Tipo_Cargo": "Diretor",
         "Tipo_Movimentacao": "Compra", "Tipo_Ativo": "Ação",
         "Quantidade": 10000, "Preco_Unitario": 38.5, "Volume": 385000,
         "Descricao_Movimentacao": "Compra de ações"},
        {"Data_Movimentacao": "2026-07-10", "Tipo_Cargo": "Diretor",
         "Tipo_Movimentacao": "Venda", "Tipo_Ativo": "Ação",
         "Quantidade": 5000, "Preco_Unitario": 37.8, "Volume": 189000,
         "Descricao_Movimentacao": "Venda de ações"},
    ],
}

MOCK_BY_ROLE = {
    "status": "ok", "company": "PETR4", "cnpj": "33000167000101", "count": 1,
    "by_role": [
        {"Tipo_Cargo": "Diretor", "transaction_count": 2,
         "total_bought": 10000, "total_sold": 5000,
         "volume_bought": 385000, "volume_sold": 189000,
         "earliest_date": "2026-07-10", "latest_date": "2026-07-15"},
    ],
}

MOCK_SUMMARY = {
    "status": "ok", "company": "PETR4", "cnpj": "33000167000101", "count": 1,
    "monthly": [
        {"month": "2026-07", "transaction_count": 2,
         "bought": 10000, "sold": 5000,
         "volume_bought": 385000, "volume_sold": 189000,
         "net_shares": 5000, "net_volume": 196000},
    ],
}


def _mock_query(monkeypatch, return_map):
    """Mock the VLMO query_engine.query function to return synthetic data
    based on the call's `summary` / `by_role` flags."""
    def fake_query(company="", limit=50, by_role=False, summary=False, **kwargs):
        if summary:
            return return_map.get("summary", MOCK_SUMMARY)
        elif by_role:
            return return_map.get("by_role", MOCK_BY_ROLE)
        else:
            return return_map.get("history", MOCK_HISTORY)
    monkeypatch.setattr("data_sources.cvm.vlmo.query_engine.query", fake_query)


class TestDashboardMode:
    def test_dashboard_no_company(self):
        """Empty company -> status=error with 'company is required'.

        The dashboard short-circuits before any underlying skill is called.
        """
        r = dashboard()
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dashboard_basic_shape(self, monkeypatch):
        """Dashboard returns status=ok with top-level tabs + kpis lists."""
        _mock_query(monkeypatch, {})
        r = dashboard(company="PETR4")
        assert r["status"] == "ok"
        assert "tabs" in r
        assert "kpis" in r
        assert isinstance(r["tabs"], list)
        assert isinstance(r["kpis"], list)

    def test_dashboard_tab_names(self, monkeypatch):
        """Tabs are exactly ['Overview', 'Recent Transactions', 'By Role',
        'Monthly Net']."""
        _mock_query(monkeypatch, {})
        r = dashboard(company="PETR4")
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Recent Transactions",
                         "By Role", "Monthly Net"]
        # Each tab has a non-empty sections list.
        for t in r["tabs"]:
            assert isinstance(t["sections"], list)
            assert len(t["sections"]) >= 1

    def test_dashboard_top_level_kpis(self, monkeypatch):
        """4 KPI cards at the top level with exact labels + unit fields."""
        _mock_query(monkeypatch, {})
        r = dashboard(company="PETR4")
        assert len(r["kpis"]) == 4
        labels = [k["label"] for k in r["kpis"]]
        assert labels == ["Sentimento", "Volume Comprado",
                          "Volume Vendido", "Net Volume"]
        # Each KPI has label + value + unit.
        for k in r["kpis"]:
            assert "label" in k
            assert "value" in k
            assert "unit" in k

    def test_dashboard_degrades_when_sub_calls_fail(self, monkeypatch):
        """When summary()/history()/by_role() ALL return error payloads,
        the dashboard still renders status=ok with 4 tabs + all KPIs as "—"."""
        def fake_query(company="", limit=50, by_role=False, summary=False, **kw):
            return {"status": "not_synced", "error": "vlmo.db missing"}
        monkeypatch.setattr("data_sources.cvm.vlmo.query_engine.query", fake_query)
        r = dashboard(company="PETR4")
        assert r["status"] == "ok"
        assert len(r["tabs"]) == 4
        # All 4 KPIs render as "—" (no data).
        for kpi in r["kpis"]:
            assert kpi["value"] == "—"
        # All tabs have a section (each table has 0 rows; Overview text shows "—").
        for t in r["tabs"]:
            assert len(t["sections"]) >= 1

    def test_route_dispatches_dashboard_mode(self, monkeypatch):
        """route(mode='dashboard') with no company returns status=error with
        'company is required'."""
        _mock_query(monkeypatch, {})
        assert "dashboard" in MANIFEST["modes"]
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dashboard_monthly_net_tab_has_chart(self, monkeypatch):
        """[v1.2] Monthly Net tab has a chart section (build_monthly_net_chart)."""
        _mock_query(monkeypatch, {})
        r = dashboard(company="PETR4")
        monthly_tab = next(t for t in r["tabs"] if t["name"] == "Monthly Net")
        types = [s.get("type") for s in monthly_tab["sections"]]
        assert "chart" in types
        # The chart section has a chart_data block with Chart.js config.
        chart = next(s for s in monthly_tab["sections"] if s.get("type") == "chart")
        assert "chart_data" in chart
        assert chart["chart_data"]["type"] == "bar"
