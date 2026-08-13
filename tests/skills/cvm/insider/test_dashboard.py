"""Tests for skills/cvm/insider/ — dashboard mode.

[v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call is expensive; we call it exactly once per file.

The mock VLMO setup mirrors `test_insider.py` (duplicated here so this
test module is self-contained).
"""
from __future__ import annotations

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

    def test_dashboard_tab_structure(self, monkeypatch):
        """Tabs are exactly ['Overview', 'Recent Transactions', 'By Role',
        'Monthly Net']."""
        _mock_query(monkeypatch, {})
        r = dashboard(company="PETR4")
        assert r["status"] == "ok"
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Recent Transactions",
                         "By Role", "Monthly Net"]
        # Each tab has a non-empty sections list.
        for t in r["tabs"]:
            assert isinstance(t["sections"], list)
            assert len(t["sections"]) >= 1
