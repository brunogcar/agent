"""Tests for skills/cvm/financials/ — DRE mode.

Tests the new dre mode (Demonstração do Resultado do Exercício) that
surfaces DRE data from DFP. Uses mocked DFP connection — no real database
needed. Follows the same pattern as test_dva.py.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock


class TestDREMode:
    """Tests for the financials.dre() mode."""

    def test_dre_requires_company(self):
        """Empty company -> status=error."""
        from skills.cvm.financials.modes.dre import dre
        r = dre()
        assert r["status"] == "error"
        assert "company" in r["error"]

    def test_dre_company_not_found(self):
        """Company not in DFP -> status=not_found."""
        from skills.cvm.financials.modes.dre import dre

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = dre(company="UNKNOWN4")
            assert r["status"] == "not_found"
            assert "not found in DFP" in r["error"]

    def test_dre_no_dre_data(self):
        """Company exists but has no DRE rows -> status=not_found."""
        from skills.cvm.financials.modes.dre import dre

        mock_conn = MagicMock()
        # First query (year_rows) returns empty — no DRE data
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "TEST COMPANY")):
            r = dre(company="PETR4")
            assert r["status"] == "not_found"
            assert "No DRE data" in r["error"]

    def test_dre_basic_shape(self):
        """DRE mode returns status=ok with periods + accounts."""
        from skills.cvm.financials.modes.dre import dre

        # Mock rows simulating DFP DRE query results — use a simple class
        # so the row["data_fim_exerc"] indexing works (sqlite3.Row style).
        class FakeRow:
            def __init__(self, **kwargs):
                self._data = kwargs
            def __getitem__(self, key):
                return self._data[key]

        mock_year_rows = [FakeRow(data_fim_exerc="2024-12-31")]
        mock_dre_rows = [
            FakeRow(codigo="3.01", descricao="Receita Líquida",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="500000000000", escala="MILHOES"),
            FakeRow(codigo="3.02", descricao="Custo dos Bens Vendidos",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="-300000000000", escala="MILHOES"),
            FakeRow(codigo="3.03", descricao="Resultado Bruto",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="200000000000", escala="MILHOES"),
            FakeRow(codigo="3.05", descricao="Resultado Antes Tributos",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="80000000000", escala="MILHOES"),
            FakeRow(codigo="3.07", descricao="Resultado Líquido Continuadas",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="70000000000", escala="MILHOES"),
            FakeRow(codigo="3.11", descricao="Lucro Líquido Consolidado",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="50000000000", escala="MILHOES"),
        ]

        mock_conn = MagicMock()
        # First execute() returns year_rows, second returns dre_rows
        mock_conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=mock_year_rows)),
            MagicMock(fetchall=MagicMock(return_value=mock_dre_rows)),
        ]
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "PETROLEO BRASILEIRO S.A.")), \
             patch("data_sources.cvm._db.parse_escala", return_value=1000000):
            r = dre(company="PETR4", periods=1)

            assert r["status"] == "ok"
            assert r["company"] == "PETROLEO BRASILEIRO S.A."
            assert r["period_type"] == "annual"
            assert len(r["periods"]) == 1

            period = r["periods"][0]
            assert period["data_fim_exerc"] == "2024-12-31"
            assert period["meses"] == 12

            accounts = period["accounts"]
            assert "3.01" in accounts  # Receita Líquida
            assert "3.02" in accounts  # Custos
            assert "3.03" in accounts  # Resultado Bruto
            assert "3.05" in accounts  # EBIT
            assert "3.07" in accounts  # Resultado Líquido Continuadas (NEW v1.8)
            assert "3.11" in accounts  # Lucro Líquido

            # Check label + section + value
            receita = accounts["3.01"]
            assert receita["label"] == "Receita Líquida de Vendas e/ou Serviços"
            assert receita["section"] == "revenue"
            assert receita["valor_brl"] == 500000000000 * 1000000  # escala applied

            lucro_liq = accounts["3.11"]
            assert lucro_liq["section"] == "net_income_alt"

            # 3.07 has its own section
            continuadas = accounts["3.07"]
            assert continuadas["section"] == "net_continuing"

    def test_dre_route_dispatches(self):
        """route(mode='dre') dispatches to the dre function."""
        from skills.cvm.financials import route
        r = route(mode="dre")
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dre_route_dispatches_with_params(self):
        """route(mode='dre', company='PETR4', quarterly=1) dispatches with quarterly param."""
        from skills.cvm.financials import route, MANIFEST
        from unittest.mock import patch, MagicMock
        assert "dre" in MANIFEST["modes"]
        # Mock the DFP connection so it doesn't depend on a real DB
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()
        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = route(mode="dre", company="UNKNOWN4", quarterly=1, periods=4)
            assert r["status"] in ("error", "not_synced", "not_found")

    def test_dre_accepts_quarterly_param(self):
        """[v1.8] dre() accepts quarterly=1 param."""
        from skills.cvm.financials.modes.dre import dre

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = dre(company="UNKNOWN4", quarterly=1)
            assert r["status"] == "not_found"

    def test_dre_route_registered_in_manifest(self):
        """[v1.8] 'dre' mode is registered in MANIFEST['modes'] with correct shape."""
        from skills.cvm.financials import MANIFEST
        dre_spec = MANIFEST["modes"].get("dre")
        assert dre_spec is not None, "dre mode should be registered"
        # All 4 params should be documented
        params = dre_spec.get("params", {})
        assert "company" in params
        assert "periods" in params
        assert "consolidado" in params
        assert "quarterly" in params
