"""Tests for skills/cvm/financials/ — DVA mode.

Tests the new dva mode (Demonstração do Valor Adicionado) that surfaces
DVA data from DFP. Uses mocked DFP connection — no real database needed.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock


class TestDVAMode:
    """Tests for the financials.dva() mode."""

    def test_dva_requires_company(self):
        """Empty company -> status=error."""
        from skills.cvm.financials.modes.dva import dva
        r = dva()
        assert r["status"] == "error"
        assert "company" in r["error"]

    def test_dva_company_not_found(self):
        """Company not in DFP -> status=not_found."""
        from skills.cvm.financials.modes.dva import dva

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = dva(company="UNKNOWN4")
            assert r["status"] == "not_found"
            assert "not found in DFP" in r["error"]

    def test_dva_no_dva_data(self):
        """Company exists but has no DVA rows -> status=not_found."""
        from skills.cvm.financials.modes.dva import dva

        mock_conn = MagicMock()
        # First query (year_rows) returns empty — no DVA data
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "TEST COMPANY")):
            r = dva(company="PETR4")
            assert r["status"] == "not_found"
            assert "No DVA data" in r["error"]

    def test_dva_basic_shape(self):
        """DVA mode returns status=ok with periods + accounts."""
        from skills.cvm.financials.modes.dva import dva

        # Mock rows simulating DFP DVA query results — use a simple class
        # so the row["data_fim_exerc"] indexing works (sqlite3.Row style).
        class FakeRow:
            def __init__(self, **kwargs):
                self._data = kwargs
            def __getitem__(self, key):
                return self._data[key]

        mock_year_rows = [FakeRow(data_fim_exerc="2024-12-31")]
        mock_dva_rows = [
            FakeRow(codigo="7.01", descricao="Receitas", data_fim_exerc="2024-12-31",
                    meses=12, valor="50000000000", escala="MILHOES"),
            FakeRow(codigo="7.03", descricao="Insumos", data_fim_exerc="2024-12-31",
                    meses=12, valor="-30000000000", escala="MILHOES"),
            FakeRow(codigo="7.04", descricao="Valor Adicionado Bruto",
                    data_fim_exerc="2024-12-31", meses=12, valor="20000000000", escala="MILHOES"),
            FakeRow(codigo="7.08", descricao="Valor Adicionado Total a Distribuir",
                    data_fim_exerc="2024-12-31", meses=12, valor="15000000000", escala="MILHOES"),
            FakeRow(codigo="7.08.01", descricao="Pessoal", data_fim_exerc="2024-12-31",
                    meses=12, valor="5000000000", escala="MILHOES"),
            FakeRow(codigo="7.08.04", descricao="Remuneração de Capital Próprio",
                    data_fim_exerc="2024-12-31", meses=12, valor="3000000000", escala="MILHOES"),
        ]

        mock_conn = MagicMock()
        # First execute() returns year_rows, second returns dva_rows
        mock_conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=mock_year_rows)),
            MagicMock(fetchall=MagicMock(return_value=mock_dva_rows)),
        ]
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "PETROLEO BRASILEIRO S.A.")), \
             patch("data_sources.cvm._db.parse_escala", return_value=1000000):
            r = dva(company="PETR4", periods=1)

            assert r["status"] == "ok"
            assert r["company"] == "PETROLEO BRASILEIRO S.A."
            assert len(r["periods"]) == 1

            period = r["periods"][0]
            assert period["data_fim_exerc"] == "2024-12-31"

            accounts = period["accounts"]
            assert "7.01" in accounts  # Receitas
            assert "7.03" in accounts  # Insumos
            assert "7.04" in accounts  # Valor Adicionado Bruto
            assert "7.08" in accounts  # Total a Distribuir
            assert "7.08.01" in accounts  # Pessoal
            assert "7.08.04" in accounts  # Remuneração Capital Próprio

            # Check label + section + value
            receitas = accounts["7.01"]
            assert receitas["label"] == "Receitas"
            assert receitas["section"] == "generation"
            assert receitas["valor_brl"] == 50000000000 * 1000000  # escala applied

            pessoal = accounts["7.08.01"]
            assert pessoal["label"] == "Pessoal"
            assert pessoal["section"] == "distribution"

    def test_dva_route_dispatches(self):
        """route(mode='dva') dispatches to the dva function."""
        from skills.cvm.financials import route
        r = route(mode="dva")
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dva_route_dispatches_with_params(self):
        """route(mode='dva', company='PETR4', quarterly=1) dispatches with quarterly param."""
        from skills.cvm.financials import route, MANIFEST
        from unittest.mock import patch, MagicMock
        assert "dva" in MANIFEST["modes"]
        # Mock the DFP connection so it doesn't depend on a real DB
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()
        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = route(mode="dva", company="UNKNOWN4", quarterly=1, periods=4)
            assert r["status"] in ("error", "not_synced", "not_found")

    def test_dva_accepts_quarterly_param(self):
        """[v1.7] dva() accepts quarterly=1 param."""
        from skills.cvm.financials.modes.dva import dva

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = dva(company="UNKNOWN4", quarterly=1)
            assert r["status"] == "not_found"
