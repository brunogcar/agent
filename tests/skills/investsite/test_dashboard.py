"""Tests for skills/investsite/ — dashboard mode.

[v2.0] Updated for 12-tab structure with sidebar groups + statements.

Covers:
  - no ticker -> short-circuit error
  - basic shape (status, tabs, kpis lists)
  - 12 tabs with sidebar groups
  - top-level KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield)
  - degradation when indicators() + events() raise ConnectionError
  - route dispatches to dashboard mode
"""
from __future__ import annotations

from skills.investsite import MANIFEST, route
from skills.investsite.modes.dashboard import dashboard


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_fetches(monkeypatch):
    """Mock fetch_page + parse_indicators + parse_events + parse_statement."""
    def fake_fetch_page(path, params=None, force=False):
        return "<html></html>"

    def fake_parse_indicators(html):
        return {
            "status": "ok",
            "ticker": "PETR4",
            "sections": {
                "dados_basicos": {"Empresa": "PETROBRAS", "Setor": "Petróleo"},
                "precos_relativos": {
                    "Preco/Lucro": 8.5,
                    "Preco/VPA": 1.9,
                    "EV/EBITDA": 4.5,
                    "Dividend Yield": 0.12,
                },
                "retornos_margens": {
                    "Retorno s/ Patrimonio Liquido": 0.25,
                    "Margem EBITDA": 0.35,
                },
                "balanco_patrimonial": {"Caixa": 50000000000},
                "dre_ttm": {"Receita Liquida": 300000000000},
                "experimental": {"CAPEX": 10000000000},
            },
        }

    def fake_parse_events(html, categoria=""):
        return {
            "status": "ok",
            "ticker": "PETR4",
            "events": [
                {"data_entrega": "2024-06-15", "data_referencia": "2024-06-14",
                 "categoria": "Fato Relevante", "tipo": "IPE", "especie": "",
                 "assuntos": "Test event", "link_cvm": "https://example.com"},
            ],
        }

    def fake_parse_statement(html, statement_type=""):
        return {
            "status": "ok",
            "statement_type": statement_type,
            "period_headers": ["2024-12-31", "2023-12-31"],
            "accounts": [
                {"codigo": "1", "descricao": "Ativo Total",
                 "periods": [{"value": "R$ 500B", "pct_total": "100%"}, {"value": "R$ 450B", "pct_total": "100%"}]},
            ],
            "account_count": 1,
        }

    monkeypatch.setattr("skills.investsite.modes.indicators.fetch_page", fake_fetch_page)
    monkeypatch.setattr("skills.investsite.modes.events.fetch_page", fake_fetch_page)
    monkeypatch.setattr("skills.investsite.modes.statements.fetch_page", fake_fetch_page)
    monkeypatch.setattr("skills.investsite.modes.indicators.parse_indicators", fake_parse_indicators)
    monkeypatch.setattr("skills.investsite.modes.events.parse_events", fake_parse_events)
    monkeypatch.setattr("skills.investsite.modes.statements.parse_statement", fake_parse_statement)


class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker -> status=error."""
        r = dashboard()
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]

    def test_dashboard_basic_shape(self, monkeypatch):
        """Dashboard returns status=ok with top-level tabs + kpis lists."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        assert r["status"] == "ok"
        assert "tabs" in r
        assert "kpis" in r
        assert isinstance(r["tabs"], list)
        assert isinstance(r["kpis"], list)

    def test_dashboard_tab_count_and_groups(self, monkeypatch):
        """[v2.1] 11 tabs with 4 sidebar groups (BPA+BPP combined into Balanço)."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        assert r["status"] == "ok"
        assert len(r["tabs"]) == 11
        # Every tab has a group field.
        groups = [t.get("group") for t in r["tabs"]]
        assert "Resumo" in groups
        assert "Análise" in groups
        assert "Demonstrações" in groups
        assert "Corporativo" in groups

    def test_dashboard_top_level_kpis(self, monkeypatch):
        """5 KPI cards at the top level."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        assert len(r["kpis"]) == 5
        labels = [k["label"] for k in r["kpis"]]
        assert labels == ["P/L", "P/VPA", "EV/EBITDA", "ROE", "Dividend Yield"]

    def test_dashboard_degrades_when_sub_calls_fail(self, monkeypatch):
        """When all fetches fail, dashboard still renders."""
        def boom(*args, **kwargs):
            raise ConnectionError("Network error")
        monkeypatch.setattr("skills.investsite.modes.indicators.fetch_page", boom)
        monkeypatch.setattr("skills.investsite.modes.events.fetch_page", boom)
        monkeypatch.setattr("skills.investsite.modes.statements.fetch_page", boom)
        r = dashboard(ticker="PETR4")
        assert r["status"] == "ok"
        assert len(r["tabs"]) == 11
        for k in r["kpis"]:
            assert k["value"] == "—"

    def test_route_dispatches_dashboard_mode(self, monkeypatch):
        """route(mode='dashboard') with no ticker returns error."""
        _mock_fetches(monkeypatch)
        assert "dashboard" in MANIFEST["modes"]
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]

    def test_dashboard_has_company_header(self, monkeypatch):
        """[v2.0] Dashboard returns company_header dict."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        assert "company_header" in r
        assert r["company_header"]["ticker"] == "PETR4"
        assert r["company_header"]["name"] == "PETROBRAS"

    def test_dashboard_has_freshness_footer(self, monkeypatch):
        """[v2.0] Dashboard returns freshness_footer string."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        assert "freshness_footer" in r
        assert "investsite.com.br" in r["freshness_footer"]
