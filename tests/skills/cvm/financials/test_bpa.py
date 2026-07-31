"""Tests for skills/cvm/financials/ — BPA mode.

Tests the new bpa mode (Balanço Patrimonial Ativo — Balance Sheet Assets)
that surfaces BPA data from DFP. Uses mocked DFP connection — no real
database needed. Follows the same pattern as test_dva.py / test_dre.py.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock


class TestBPAMode:
    """Tests for the financials.bpa() mode."""

    def test_bpa_requires_company(self):
        """Empty company -> status=error."""
        from skills.cvm.financials.modes.bpa import bpa
        r = bpa()
        assert r["status"] == "error"
        assert "company" in r["error"]

    def test_bpa_company_not_found(self):
        """Company not in DFP -> status=not_found."""
        from skills.cvm.financials.modes.bpa import bpa

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = bpa(company="UNKNOWN4")
            assert r["status"] == "not_found"
            assert "not found in DFP" in r["error"]

    def test_bpa_no_bpa_data(self):
        """Company exists but has no BPA rows -> status=not_found."""
        from skills.cvm.financials.modes.bpa import bpa

        mock_conn = MagicMock()
        # First query (year_rows) returns empty — no BPA data
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "TEST COMPANY")):
            r = bpa(company="PETR4")
            assert r["status"] == "not_found"
            assert "No BPA data" in r["error"]

    def test_bpa_basic_shape(self):
        """BPA mode returns status=ok with periods + accounts."""
        from skills.cvm.financials.modes.bpa import bpa

        # Mock rows simulating DFP BPA query results — use a simple class
        # so the row["data_fim_exerc"] indexing works (sqlite3.Row style).
        class FakeRow:
            def __init__(self, **kwargs):
                self._data = kwargs
            def __getitem__(self, key):
                return self._data[key]

        mock_year_rows = [FakeRow(data_fim_exerc="2024-12-31")]
        mock_bpa_rows = [
            FakeRow(codigo="1", descricao="Ativo Total",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="100000000000", escala="MILHOES"),
            FakeRow(codigo="1.01", descricao="Ativo Circulante",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="30000000000", escala="MILHOES"),
            FakeRow(codigo="1.01.01", descricao="Caixa e Equivalentes",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="5000000000", escala="MILHOES"),
            FakeRow(codigo="1.01.03", descricao="Contas a Receber",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="8000000000", escala="MILHOES"),
            FakeRow(codigo="1.01.04", descricao="Estoques",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="6000000000", escala="MILHOES"),
            FakeRow(codigo="1.02", descricao="Ativo Não Circulante",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="70000000000", escala="MILHOES"),
            FakeRow(codigo="1.02.03", descricao="Imobilizado",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="45000000000", escala="MILHOES"),
            FakeRow(codigo="1.02.04", descricao="Intangível",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="15000000000", escala="MILHOES"),
        ]

        mock_conn = MagicMock()
        # First execute() returns year_rows, second returns bpa_rows
        mock_conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=mock_year_rows)),
            MagicMock(fetchall=MagicMock(return_value=mock_bpa_rows)),
        ]
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "PETROLEO BRASILEIRO S.A.")), \
             patch("data_sources.cvm._db.parse_escala", return_value=1000000):
            r = bpa(company="PETR4", periods=1)

            assert r["status"] == "ok"
            assert r["company"] == "PETROLEO BRASILEIRO S.A."
            assert r["period_type"] == "annual"
            assert len(r["periods"]) == 1

            period = r["periods"][0]
            assert period["data_fim_exerc"] == "2024-12-31"
            assert period["meses"] == 12

            accounts = period["accounts"]
            assert "1" in accounts        # Ativo Total
            assert "1.01" in accounts     # Ativo Circulante
            assert "1.01.01" in accounts  # Caixa
            assert "1.01.03" in accounts  # Contas a Receber
            assert "1.01.04" in accounts  # Estoques
            assert "1.02" in accounts     # Ativo Não Circulante
            assert "1.02.03" in accounts  # Imobilizado
            assert "1.02.04" in accounts  # Intangível

            # Check label + section + value
            ativo_total = accounts["1"]
            assert ativo_total["label"] == "Ativo Total"
            assert ativo_total["section"] == "total"
            assert ativo_total["valor_brl"] == 100000000000 * 1000000  # escala applied

            caixa = accounts["1.01.01"]
            assert caixa["label"] == "Caixa e Equivalentes"
            assert caixa["section"] == "cash"

            imobilizado = accounts["1.02.03"]
            assert imobilizado["label"] == "Imobilizado"
            assert imobilizado["section"] == "ppe"

    def test_bpa_route_dispatches(self):
        """route(mode='bpa') dispatches to the bpa function."""
        from skills.cvm.financials import route
        r = route(mode="bpa")
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_bpa_route_dispatches_with_params(self):
        """route(mode='bpa', company='PETR4', quarterly=1) dispatches with quarterly param."""
        from skills.cvm.financials import route, MANIFEST
        from unittest.mock import patch, MagicMock
        assert "bpa" in MANIFEST["modes"]
        # Mock the DFP connection so it doesn't depend on a real DB
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()
        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = route(mode="bpa", company="UNKNOWN4", quarterly=1, periods=4)
            assert r["status"] in ("error", "not_synced", "not_found")

    def test_bpa_accepts_quarterly_param(self):
        """[v1.9] bpa() accepts quarterly=1 param."""
        from skills.cvm.financials.modes.bpa import bpa

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = bpa(company="UNKNOWN4", quarterly=1)
            assert r["status"] == "not_found"

    def test_bpa_route_registered_in_manifest(self):
        """[v1.9] 'bpa' mode is registered in MANIFEST['modes'] with correct shape."""
        from skills.cvm.financials import MANIFEST
        bpa_spec = MANIFEST["modes"].get("bpa")
        assert bpa_spec is not None, "bpa mode should be registered"
        # All 4 params should be documented
        params = bpa_spec.get("params", {})
        assert "company" in params
        assert "periods" in params
        assert "consolidado" in params
        assert "quarterly" in params

    def test_bpa_codes_complete(self):
        """[v1.9] bpa mode includes all 16 codes (1, 1.01-1.08, with sub-codes)."""
        from skills.cvm.financials.modes.bpa import _BPA_CODES
        codes = [c[0] for c in _BPA_CODES]
        # All expected codes
        expected = ["1", "1.01", "1.01.01", "1.01.02", "1.01.03", "1.01.04",
                    "1.02", "1.02.01", "1.02.03", "1.02.04",
                    "1.03", "1.04", "1.05", "1.06", "1.07", "1.08"]
        assert codes == expected, f"BPA codes mismatch: {codes}"

        # All sections are unique-ish and well-formed
        sections = [c[2] for c in _BPA_CODES]
        assert "total" in sections
        assert "current" in sections
        assert "cash" in sections
        assert "ppe" in sections
        assert "intangibles" in sections

        # NEW chart codes (1.07, 1.08) have distinct sections
        assert "ppe_new" in sections
        assert "intangibles_new" in sections
