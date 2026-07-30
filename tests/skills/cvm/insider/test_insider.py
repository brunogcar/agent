"""Tests for skills/cvm/insider/ — insider trading skill.

Uses mocked VLMO query_engine — no database needed.

[v1.1] Per-mode tests now import their mode function directly from
`skills.cvm.insider.modes.<mode>` (was `from skills.cvm.insider import insider`
before the v1.1 modular split).
"""
from __future__ import annotations

import pytest

from skills.cvm.insider.modes.history import history
from skills.cvm.insider.modes.by_role import by_role
from skills.cvm.insider.modes.summary import summary


# ── Synthetic data ───────────────────────────────────────────────────────────

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
    def fake_query(company="", limit=50, by_role=False, summary=False, **kwargs):
        if summary:
            return return_map.get("summary", MOCK_SUMMARY)
        elif by_role:
            return return_map.get("by_role", MOCK_BY_ROLE)
        else:
            return return_map.get("history", MOCK_HISTORY)
    monkeypatch.setattr("data_sources.cvm.vlmo.query_engine.query", fake_query)


# ── Input validation ─────────────────────────────────────────────────────────

class TestValidation:
    def test_history_requires_company(self):
        r = history()
        assert r["status"] == "error"

    def test_by_role_requires_company(self):
        r = by_role()
        assert r["status"] == "error"

    def test_summary_requires_company(self):
        r = summary()
        assert r["status"] == "error"


# ── History mode ─────────────────────────────────────────────────────────────

class TestHistory:
    def test_history_basic(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = history(company="PETR4", limit=10)
        assert r["status"] == "ok"
        assert r["count"] == 2
        assert len(r["movements"]) == 2

    def test_history_has_freshness(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = history(company="PETR4")
        assert "data_freshness" in r


# ── By role mode ─────────────────────────────────────────────────────────────

class TestByRole:
    def test_by_role_basic(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = by_role(company="PETR4")
        assert r["status"] == "ok"
        assert len(r["by_role"]) == 1
        assert r["by_role"][0]["Tipo_Cargo"] == "Diretor"


# ── Summary mode ─────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_basic(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = summary(company="PETR4")
        assert r["status"] == "ok"
        assert len(r["monthly"]) == 1

    def test_summary_computes_sentiment(self, monkeypatch):
        _mock_query(monkeypatch, {})
        r = summary(company="PETR4")
        assert r["sentiment"] == "buying"  # 385000 bought > 189000 sold
        assert r["net_volume"] == 196000
        assert r["total_volume_bought"] == 385000
        assert r["total_volume_sold"] == 189000


# ── Route dispatch ───────────────────────────────────────────────────────────

class TestRoute:
    def test_route_no_mode_errors(self):
        from skills.cvm.insider import route
        r = route()
        assert r["status"] == "error"

    def test_route_unknown_mode_errors(self):
        from skills.cvm.insider import route
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]

    def test_route_dashboard_dispatches(self):
        """[v1.1] New dashboard mode is reachable via the router."""
        from skills.cvm.insider import MANIFEST, route
        assert "dashboard" in MANIFEST["modes"]
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "company is required" in r["error"]
