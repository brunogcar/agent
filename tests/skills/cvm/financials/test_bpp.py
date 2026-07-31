"""Tests for skills/cvm/financials/ — BPP mode.

Tests the new bpp mode (Balanço Patrimonial Passivo — Balance Sheet
Liabilities + Equity) that surfaces BPP data from DFP. Uses mocked DFP
connection — no real database needed. Follows the same pattern as
test_bpa.py / test_dva.py / test_dre.py.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock


class TestBPPMode:
    """Tests for the financials.bpp() mode."""

    def test_bpp_requires_company(self):
        """Empty company -> status=error."""
        from skills.cvm.financials.modes.bpp import bpp
        r = bpp()
        assert r["status"] == "error"
        assert "company" in r["error"]

    def test_bpp_company_not_found(self):
        """Company not in DFP -> status=not_found."""
        from skills.cvm.financials.modes.bpp import bpp

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = bpp(company="UNKNOWN4")
            assert r["status"] == "not_found"
            assert "not found in DFP" in r["error"]

    def test_bpp_no_bpp_data(self):
        """Company exists but has no BPP rows -> status=not_found."""
        from skills.cvm.financials.modes.bpp import bpp

        mock_conn = MagicMock()
        # First query (year_rows) returns empty — no BPP data
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "TEST COMPANY")):
            r = bpp(company="PETR4")
            assert r["status"] == "not_found"
            assert "No BPP data" in r["error"]

    def test_bpp_basic_shape(self):
        """BPP mode returns status=ok with periods + accounts."""
        from skills.cvm.financials.modes.bpp import bpp

        # Mock rows simulating DFP BPP query results — use a simple class
        # so the row["data_fim_exerc"] indexing works (sqlite3.Row style).
        class FakeRow:
            def __init__(self, **kwargs):
                self._data = kwargs
            def __getitem__(self, key):
                return self._data[key]

        mock_year_rows = [FakeRow(data_fim_exerc="2024-12-31")]
        mock_bpp_rows = [
            FakeRow(codigo="2", descricao="Passivo Total",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="100000000000", escala="MILHOES"),
            FakeRow(codigo="2.01", descricao="Passivo Circulante",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="30000000000", escala="MILHOES"),
            FakeRow(codigo="2.01.01", descricao="Obrigações Sociais e Trabalhistas",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="8000000000", escala="MILHOES"),
            FakeRow(codigo="2.01.04", descricao="Empréstimos e Financiamentos",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="5000000000", escala="MILHOES"),
            FakeRow(codigo="2.02", descricao="Passivo Não Circulante",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="30000000000", escala="MILHOES"),
            FakeRow(codigo="2.02.01", descricao="Empréstimos e Financiamentos (NC)",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="15000000000", escala="MILHOES"),
            FakeRow(codigo="2.03", descricao="Patrimônio Líquido",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="40000000000", escala="MILHOES"),
            FakeRow(codigo="2.03.01", descricao="Capital Social",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="20000000000", escala="MILHOES"),
            FakeRow(codigo="2.03.02", descricao="Reservas de Capital",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="3000000000", escala="MILHOES"),
            FakeRow(codigo="2.03.04", descricao="Reservas de Lucros",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="10000000000", escala="MILHOES"),
            FakeRow(codigo="2.03.05", descricao="Lucros Acumulados",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="5000000000", escala="MILHOES"),
            FakeRow(codigo="2.03.09", descricao="Participação Não Controladores",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="2000000000", escala="MILHOES"),
        ]

        mock_conn = MagicMock()
        # First execute() returns year_rows, second returns bpp_rows
        mock_conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=mock_year_rows)),
            MagicMock(fetchall=MagicMock(return_value=mock_bpp_rows)),
        ]
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "PETROLEO BRASILEIRO S.A.")), \
             patch("data_sources.cvm._db.parse_escala", return_value=1000000):
            r = bpp(company="PETR4", periods=1)

            assert r["status"] == "ok"
            assert r["company"] == "PETROLEO BRASILEIRO S.A."
            assert r["period_type"] == "annual"
            assert len(r["periods"]) == 1

            period = r["periods"][0]
            assert period["data_fim_exerc"] == "2024-12-31"
            assert period["meses"] == 12

            accounts = period["accounts"]
            assert "2" in accounts          # Passivo Total
            assert "2.01" in accounts       # Passivo Circulante
            assert "2.01.01" in accounts    # Fornecedores / Obrigações (NEW v1.10)
            assert "2.01.04" in accounts    # Empréstimos Circulante
            assert "2.02" in accounts       # Passivo Não Circulante
            assert "2.02.01" in accounts    # Empréstimos Não Circulante
            assert "2.03" in accounts       # Patrimônio Líquido
            assert "2.03.01" in accounts    # Capital Social (NEW v1.10)
            assert "2.03.02" in accounts    # Reservas de Capital (NEW v1.10)
            assert "2.03.04" in accounts    # Reservas de Lucros (NEW v1.10)
            assert "2.03.05" in accounts    # Lucros Acumulados (NEW v1.10)
            assert "2.03.09" in accounts    # Participação Não Controladores (NEW v1.10)

            # Check label + section + value
            passivo_total = accounts["2"]
            assert passivo_total["label"] == "Passivo Total"
            assert passivo_total["section"] == "total"
            assert passivo_total["valor_brl"] == 100000000000 * 1000000  # escala applied

            pl = accounts["2.03"]
            assert pl["label"] == "Patrimônio Líquido"
            assert pl["section"] == "equity"

            capital_social = accounts["2.03.01"]
            assert capital_social["label"] == "Capital Social"
            assert capital_social["section"] == "capital"

            fornecedores = accounts["2.01.01"]
            assert fornecedores["label"] == "Fornecedores / Obrigações"
            assert fornecedores["section"] == "payables"

            minority = accounts["2.03.09"]
            assert minority["label"] == "Participação Não Controladores"
            assert minority["section"] == "minority"

    def test_bpp_route_dispatches(self):
        """route(mode='bpp') dispatches to the bpp function."""
        from skills.cvm.financials import route
        r = route(mode="bpp")
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_bpp_route_dispatches_with_params(self):
        """route(mode='bpp', company='PETR4', quarterly=1) dispatches with quarterly param."""
        from skills.cvm.financials import route, MANIFEST
        from unittest.mock import patch, MagicMock
        assert "bpp" in MANIFEST["modes"]
        # Mock the DFP connection so it doesn't depend on a real DB
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()
        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = route(mode="bpp", company="UNKNOWN4", quarterly=1, periods=4)
            assert r["status"] in ("error", "not_synced", "not_found")

    def test_bpp_accepts_quarterly_param(self):
        """[v1.10] bpp() accepts quarterly=1 param."""
        from skills.cvm.financials.modes.bpp import bpp

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = bpp(company="UNKNOWN4", quarterly=1)
            assert r["status"] == "not_found"

    def test_bpp_route_registered_in_manifest(self):
        """[v1.10] 'bpp' mode is registered in MANIFEST['modes'] with correct shape."""
        from skills.cvm.financials import MANIFEST
        bpp_spec = MANIFEST["modes"].get("bpp")
        assert bpp_spec is not None, "bpp mode should be registered"
        # All 4 params should be documented
        params = bpp_spec.get("params", {})
        assert "company" in params
        assert "periods" in params
        assert "consolidado" in params
        assert "quarterly" in params

    def test_bpp_codes_complete(self):
        """[v1.10] bpp mode includes all 17 codes (2, 2.01-2.08, with sub-codes)."""
        from skills.cvm.financials.modes.bpp import _BPP_CODES
        codes = [c[0] for c in _BPP_CODES]
        # All expected codes — 12 OLD chart codes + 5 NEW chart codes
        expected = ["2", "2.01", "2.01.01", "2.01.04", "2.02", "2.02.01",
                    "2.03", "2.03.01", "2.03.02", "2.03.04", "2.03.05", "2.03.09",
                    "2.04", "2.05", "2.06", "2.07", "2.08"]
        assert codes == expected, f"BPP codes mismatch: {codes}"

        # All sections are unique-ish and well-formed
        sections = [c[2] for c in _BPP_CODES]
        assert "total" in sections
        assert "current" in sections
        assert "payables" in sections
        assert "debt_short" in sections
        assert "debt_long" in sections
        assert "equity" in sections
        assert "capital" in sections
        assert "reserves_capital" in sections
        assert "reserves_profit" in sections
        assert "retained_earnings" in sections
        assert "minority" in sections

        # NEW chart codes (2.04-2.08) have distinct sections
        assert "provisions_new" in sections
        assert "tax_liabilities_new" in sections
        assert "other_liabilities_new" in sections
        assert "non_current_new" in sections
        assert "equity_new" in sections
