"""tests/skills/investsite/test_investsite.py -- Tests for investsite skill.

Mocks HTTP fetcher — no real network calls. Tests all 5 modes + parsers.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch


# ── Synthetic HTML fixtures ──────────────────────────────────────────────────

INDICATORS_HTML = """
<html><body>
<table>
<caption>Dados Básicos da Empresa</caption>
<tr><td>Empresa</td><td>PETROBRAS</td></tr>
<tr><td>Razão Social</td><td>PETROLEO BRASILEIRO S.A.</td></tr>
<tr><td>Ação</td><td>PETR4</td></tr>
</table>
<table>
<caption>Preços Relativos, Market Cap, EV, e Dividend Yield</caption>
<tr><td>Consolidado</td><td>Atual</td></tr>
<tr><td>Preço/Lucro</td><td>5,15</td></tr>
<tr><td>Preço/VPA</td><td>1,24</td></tr>
<tr><td>Dividend Yield</td><td>0,15</td></tr>
</table>
<table>
<caption>Resumo DRE Últimos Doze Meses</caption>
<tr><td>Consolidado</td><td>31/03/2026</td></tr>
<tr><td>Receita Líquida</td><td>R$ 498,09 B</td></tr>
<tr><td>EBITDA</td><td>R$ 230,88 B</td></tr>
<tr><td>Lucro Líquido</td><td>R$ 107,58 B</td></tr>
</table>
<table>
<caption>Retornos, Margens e Outras Medidas</caption>
<tr><td>Consolidado</td><td>Atual</td></tr>
<tr><td>Retorno s/ Patrimônio Líquido</td><td>27,18%</td></tr>
<tr><td>Margem EBITDA</td><td>46,35%</td></tr>
<tr><td>Dívida Líquida/EBITDA</td><td>1,46</td></tr>
</table>
<table>
<caption>Resumo Balanço Patrimonial</caption>
<tr><td>Consolidado</td><td>31/03/2026</td></tr>
<tr><td>Caixa e Equivalentes</td><td>R$ 34,29 B</td></tr>
<tr><td>Ativo Total</td><td>R$ 1,25 T</td></tr>
<tr><td>Dívida Bruta</td><td>R$ 371,69 B</td></tr>
</table>
<table>
<caption>Resumo Fluxo de Caixa Últimos Doze Meses</caption>
<tr><td>Consolidado</td><td>TTM</td></tr>
<tr><td>Fluxo de Caixa Operacional</td><td>R$ 194,97 B</td></tr>
</table>
<table>
<caption>Cálculo Experimental de CAPEX e Fluxo de Caixa Livre</caption>
<tr><td>Consolidado</td><td>12 meses</td></tr>
<tr><td>CAPEX 12 meses</td><td>- R$ 109,15 B</td></tr>
<tr><td>Fluxo de Caixa Livre 12 meses</td><td>R$ 85,82 B</td></tr>
</table>
</body></html>
"""

STATEMENT_HTML = """
<html><body>
<table>
<caption>Demonstração do Resultado</caption>
<tr><th>Conta</th><th>Descrição</th><th>01/01/2026 a 31/03/2026</th><th>% total</th><th>01/01/2025 a 31/03/2025</th><th>% total</th></tr>
<tr><td>3.01</td><td>Receita de Venda</td><td>123686000</td><td>100,00%</td><td>123144000</td><td>100,00%</td></tr>
<tr><td>3.02</td><td>Custo dos Bens</td><td>-64084000</td><td>-51,81%</td><td>-62435000</td><td>-50,70%</td></tr>
<tr><td>3.03</td><td>Resultado Bruto</td><td>59602000</td><td>48,19%</td><td>60709000</td><td>49,30%</td></tr>
</table>
</body></html>
"""

EVENTS_HTML = """
<html><body>
<table>
<caption>Informações Periódicas</caption>
<tr><th>Data Entrega</th><th>Data Referência</th><th>Categoria</th><th>Tipo</th><th>Espécie</th><th>Assuntos</th></tr>
<tr><td>02/06/2026</td><td>02/06/2026</td><td>Fato Relevante</td><td></td><td></td><td><a href="https://www.rad.cvm.gov.br/ENET/frmExibirArquivoIPEExterno.aspx?ID=1529607&flnk">Petrobras informa sobre adesão</a></td></tr>
<tr><td>20/05/2026</td><td>20/05/2026</td><td>Fato Relevante</td><td></td><td></td><td><a href="https://www.rad.cvm.gov.br/ENET/frmExibirArquivoIPEExterno.aspx?ID=1525282&flnk">Petrobras informa sobre adesão</a></td></tr>
<tr><td>11/05/2026</td><td>11/05/2026</td><td>Fato Relevante</td><td></td><td></td><td><a href="https://www.rad.cvm.gov.br/ENET/frmExibirArquivoIPEExterno.aspx?ID=1520177&flnk">Petrobras informa sobre remuneração</a></td></tr>
</table>
</body></html>
"""


# ── Parser tests ─────────────────────────────────────────────────────────────

class TestParsers:

    def test_parse_indicators(self):
        from skills.investsite.parsers import parse_indicators
        result = parse_indicators(INDICATORS_HTML)
        assert result["status"] == "ok"
        sections = result["sections"]
        assert "dados_basicos" in sections
        assert "precos_relativos" in sections
        assert "dre_ttm" in sections
        assert "retornos_margens" in sections
        assert sections["dados_basicos"]["Empresa"] == "PETROBRAS"
        # [v1.0.1] Keys are now ASCII-normalized
        assert sections["precos_relativos"]["Preco/Lucro"] == "5,15"
        assert sections["retornos_margens"]["Divida Liquida/EBITDA"] == "1,46"

    def test_parse_statement(self):
        from skills.investsite.parsers import parse_statement
        result = parse_statement(STATEMENT_HTML, "DRE")
        assert result["status"] == "ok"
        assert result["statement_type"] == "DRE"
        assert result["account_count"] == 3
        accounts = result["accounts"]
        assert accounts[0]["codigo"] == "3.01"
        assert "Receita" in accounts[0]["descricao"]
        # 2 periods (current + prior year), each with value + pct
        assert len(accounts[0]["periods"]) == 2
        assert accounts[0]["periods"][0]["value"] == "123686000"
        assert accounts[0]["periods"][0]["pct_total"] == "100,00%"

    def test_parse_events(self):
        from skills.investsite.parsers import parse_events
        result = parse_events(EVENTS_HTML, "Fato Relevante")
        assert result["status"] == "ok"
        assert result["count"] == 3
        events = result["events"]
        assert events[0]["data_entrega"] == "02/06/2026"
        assert events[0]["categoria"] == "Fato Relevante"
        assert "rad.cvm.gov.br" in events[0]["link_cvm"]
        assert "1529607" in events[0]["link_cvm"]


# ── Mode tests (mocked fetcher) ──────────────────────────────────────────────

class TestIndicatorsMode:

    @patch("skills.investsite.investsite.fetch_page")
    def test_indicators_ok(self, mock_fetch):
        mock_fetch.return_value = INDICATORS_HTML
        from skills.investsite.investsite import indicators
        result = indicators(ticker="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"
        assert "precos_relativos" in result["sections"]
        assert "retornos_margens" in result["sections"]

    def test_indicators_no_ticker(self):
        from skills.investsite.investsite import indicators
        result = indicators()
        assert result["status"] == "error"

    @patch("skills.investsite.investsite.fetch_page")
    def test_indicators_fetch_error(self, mock_fetch):
        mock_fetch.side_effect = ConnectionError("Network error")
        from skills.investsite.investsite import indicators
        result = indicators(ticker="PETR4")
        assert result["status"] == "error"
        assert "Network error" in result["error"]


class TestStatementsMode:

    @patch("skills.investsite.investsite.fetch_page")
    def test_statements_ok(self, mock_fetch):
        mock_fetch.return_value = STATEMENT_HTML
        from skills.investsite.investsite import statements
        result = statements(ticker="PETR4", statement="DRE")
        assert result["status"] == "ok"
        assert result["statement_type"] == "DRE"
        assert result["account_count"] == 3

    def test_statements_no_ticker(self):
        from skills.investsite.investsite import statements
        result = statements()
        assert result["status"] == "error"

    def test_statements_invalid_type(self):
        from skills.investsite.investsite import statements
        result = statements(ticker="PETR4", statement="INVALID")
        assert result["status"] == "error"


class TestEventsMode:

    @patch("skills.investsite.investsite.fetch_page")
    def test_events_ok(self, mock_fetch):
        mock_fetch.return_value = EVENTS_HTML
        from skills.investsite.investsite import events
        result = events(ticker="PETR4", categoria="Fato Relevante")
        assert result["status"] == "ok"
        assert result["count"] == 3
        assert "rad.cvm.gov.br" in result["events"][0]["link_cvm"]

    @patch("skills.investsite.investsite.fetch_page")
    def test_events_limit(self, mock_fetch):
        mock_fetch.return_value = EVENTS_HTML
        from skills.investsite.investsite import events
        result = events(ticker="PETR4", limit=2)
        assert result["count"] == 2

    def test_events_no_ticker(self):
        from skills.investsite.investsite import events
        result = events()
        assert result["status"] == "error"


class TestSummaryMode:

    @patch("skills.investsite.investsite.fetch_page")
    def test_summary_ok(self, mock_fetch):
        # First call = indicators, second call = events
        mock_fetch.side_effect = [INDICATORS_HTML, EVENTS_HTML]
        from skills.investsite.investsite import summary
        result = summary(ticker="PETR4")
        assert result["status"] == "ok"
        assert "precos_relativos" in result["sections"]
        assert "latest_events" in result["sections"]

    def test_summary_no_ticker(self):
        from skills.investsite.investsite import summary
        result = summary()
        assert result["status"] == "error"


class TestListingMode:

    def test_listing_ok(self):
        from skills.investsite.investsite import listing
        result = listing()
        assert result["status"] == "ok"
        assert "Fato Relevante" in result["categories"]
        assert "Comunicado ao Mercado" in result["categories"]


# ── Route tests ──────────────────────────────────────────────────────────────

class TestInvestsiteRoute:

    def test_route_no_mode(self):
        from skills.investsite import route
        result = route()
        assert result["status"] == "error"
        assert "mode required" in result["error"]

    def test_route_unknown_mode(self):
        from skills.investsite import route
        result = route(mode="invalid")
        assert result["status"] == "error"
        assert "Unknown mode" in result["error"]

    def test_route_dispatches_to_listing(self):
        from skills.investsite import route
        result = route(mode="listing")
        assert result["status"] == "ok"
