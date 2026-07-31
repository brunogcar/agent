"""Tests for skills/cvm/financials/ — DFC mode.

Tests the new dfc mode (Demonstração do Fluxo de Caixa) that surfaces DFC
data from DFP. Uses mocked DFP connection — no real database needed.
Follows the same pattern as test_bpp.py / test_dre.py / test_dva.py.

[v1.11] The DFC mode filters by `grupo LIKE '%Fluxo de Caixa%'` which
matches BOTH DFC_MI (Método Indireto, 98.6% of filers) AND DFC_MD (Método
Direto, 1.4% — banks + insurers). 6 codes are surfaced: 6.01 (FCO),
6.01.01.02 (D&A), 6.02 (FCI), 6.03 (FCF), 6.04 (Variação Cambial — NEW),
6.05 (Aumento/Redução de Caixa — NEW).
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock


class TestDFCMode:
    """Tests for the financials.dfc() mode."""

    def test_dfc_requires_company(self):
        """Empty company -> status=error."""
        from skills.cvm.financials.modes.dfc import dfc
        r = dfc()
        assert r["status"] == "error"
        assert "company" in r["error"]

    def test_dfc_company_not_found(self):
        """Company not in DFP -> status=not_found."""
        from skills.cvm.financials.modes.dfc import dfc

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = dfc(company="UNKNOWN4")
            assert r["status"] == "not_found"
            assert "not found in DFP" in r["error"]

    def test_dfc_no_dfc_data(self):
        """Company exists but has no DFC rows -> status=not_found."""
        from skills.cvm.financials.modes.dfc import dfc

        mock_conn = MagicMock()
        # First query (year_rows) returns empty — no DFC data
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "TEST COMPANY")):
            r = dfc(company="PETR4")
            assert r["status"] == "not_found"
            assert "No DFC data" in r["error"]

    def test_dfc_basic_shape(self):
        """DFC mode returns status=ok with periods + accounts."""
        from skills.cvm.financials.modes.dfc import dfc

        # Mock rows simulating DFP DFC query results — use a simple class
        # so the row["data_fim_exerc"] indexing works (sqlite3.Row style).
        class FakeRow:
            def __init__(self, **kwargs):
                self._data = kwargs
            def __getitem__(self, key):
                return self._data[key]

        mock_year_rows = [FakeRow(data_fim_exerc="2024-12-31")]
        mock_dfc_rows = [
            FakeRow(codigo="6.01", descricao="Caixa Líquido Atividades Operacionais",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="180000000000", escala="MILHOES"),
            FakeRow(codigo="6.01.01.02", descricao="Depreciação e Amortização",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="30000000000", escala="MILHOES"),
            FakeRow(codigo="6.02", descricao="Caixa Líquido Atividades de Investimento",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="-80000000000", escala="MILHOES"),
            FakeRow(codigo="6.03", descricao="Caixa Líquido Atividades de Financiamento",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="-50000000000", escala="MILHOES"),
            # [v1.11] NEW codes 6.04 + 6.05
            FakeRow(codigo="6.04", descricao="Variação Cambial s/ Caixa e Equivalentes",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="-2000000000", escala="MILHOES"),
            FakeRow(codigo="6.05", descricao="Aumento (Redução) de Caixa e Equivalentes",
                    data_fim_exerc="2024-12-31", meses=12,
                    valor="48000000000", escala="MILHOES"),
        ]

        mock_conn = MagicMock()
        # First execute() returns year_rows, second returns dfc_rows
        mock_conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=mock_year_rows)),
            MagicMock(fetchall=MagicMock(return_value=mock_dfc_rows)),
        ]
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._bridge.resolve_company",
                   return_value=([1], "PETROLEO BRASILEIRO S.A.")), \
             patch("data_sources.cvm._db.parse_escala", return_value=1000000):
            r = dfc(company="PETR4", periods=1)

            assert r["status"] == "ok"
            assert r["company"] == "PETROLEO BRASILEIRO S.A."
            assert r["period_type"] == "annual"
            assert len(r["periods"]) == 1

            period = r["periods"][0]
            assert period["data_fim_exerc"] == "2024-12-31"
            assert period["meses"] == 12

            accounts = period["accounts"]
            assert "6.01" in accounts          # FCO
            assert "6.01.01.02" in accounts    # D&A
            assert "6.02" in accounts          # FCI
            assert "6.03" in accounts          # FCF
            assert "6.04" in accounts          # Variação Cambial (NEW v1.11)
            assert "6.05" in accounts          # Aumento/Redução de Caixa (NEW v1.11)

            # Check label + section + value
            fco = accounts["6.01"]
            assert fco["label"] == "Caixa Líquido Atividades Operacionais (FCO)"
            assert fco["section"] == "operating"
            assert fco["valor_brl"] == 180000000000 * 1000000  # escala applied

            da = accounts["6.01.01.02"]
            assert da["label"] == "Depreciação e Amortização"
            assert da["section"] == "da"

            fci = accounts["6.02"]
            assert fci["section"] == "investing"

            fcf = accounts["6.03"]
            assert fcf["section"] == "financing"

            # [v1.11] NEW codes have their own sections
            fx_change = accounts["6.04"]
            assert fx_change["label"] == "Variação Cambial s/ Caixa e Equivalentes"
            assert fx_change["section"] == "fx_change"

            net_change = accounts["6.05"]
            assert net_change["label"] == "Aumento (Redução) de Caixa e Equivalentes"
            assert net_change["section"] == "net_change"

    def test_dfc_route_dispatches(self):
        """route(mode='dfc') dispatches to the dfc function."""
        from skills.cvm.financials import route
        r = route(mode="dfc")
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dfc_route_dispatches_with_params(self):
        """route(mode='dfc', company='PETR4', quarterly=1) dispatches with quarterly param."""
        from skills.cvm.financials import route, MANIFEST
        from unittest.mock import patch, MagicMock
        assert "dfc" in MANIFEST["modes"]
        # Mock the DFP connection so it doesn't depend on a real DB
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()
        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = route(mode="dfc", company="UNKNOWN4", quarterly=1, periods=4)
            assert r["status"] in ("error", "not_synced", "not_found")

    def test_dfc_accepts_quarterly_param(self):
        """[v1.11] dfc() accepts quarterly=1 param."""
        from skills.cvm.financials.modes.dfc import dfc

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.close = MagicMock()

        with patch("data_sources.cvm._db.connect_dfp", return_value=mock_conn), \
             patch("data_sources.cvm._db.connect_itr", side_effect=FileNotFoundError("no itr")), \
             patch("data_sources.cvm._bridge.resolve_company", return_value=([], "")):
            r = dfc(company="UNKNOWN4", quarterly=1)
            assert r["status"] == "not_found"

    def test_dfc_route_registered_in_manifest(self):
        """[v1.11] 'dfc' mode is registered in MANIFEST['modes'] with correct shape."""
        from skills.cvm.financials import MANIFEST
        dfc_spec = MANIFEST["modes"].get("dfc")
        assert dfc_spec is not None, "dfc mode should be registered"
        # All 4 params should be documented
        params = dfc_spec.get("params", {})
        assert "company" in params
        assert "periods" in params
        assert "consolidado" in params
        assert "quarterly" in params

    def test_dfc_codes_complete(self):
        """[v1.11] dfc mode includes all 6 codes (6.01, 6.01.01.02, 6.02, 6.03, 6.04, 6.05)."""
        from skills.cvm.financials.modes.dfc import _DFC_CODES
        codes = [c[0] for c in _DFC_CODES]
        # All expected codes — 4 original + 2 NEW (6.04, 6.05)
        expected = ["6.01", "6.01.01.02", "6.02", "6.03", "6.04", "6.05"]
        assert codes == expected, f"DFC codes mismatch: {codes}"

        # All sections are unique and well-formed
        sections = [c[2] for c in _DFC_CODES]
        assert "operating" in sections
        assert "da" in sections
        assert "investing" in sections
        assert "financing" in sections
        # NEW v1.11 sections
        assert "fx_change" in sections
        assert "net_change" in sections

    def test_dfc_extract_metrics_new_keys(self):
        """[v1.11] _extract_metrics exposes variacao_cambial + variacao_caixa from 6.04 + 6.05."""
        from skills.cvm.financials.fetchers import _extract_metrics
        vals = {
            "6.01": 18000000.0,
            "6.02": -8000000.0,
            "6.03": -5000000.0,
            "6.01.01.02": 3000000.0,
            "6.04": -200000.0,
            "6.05": 4800000.0,
        }
        m = _extract_metrics(vals)
        assert m["fco"] == 18000000.0
        assert m["fci"] == -8000000.0
        assert m["fcf"] == -5000000.0
        assert m["da"] == 3000000.0
        # NEW v1.11 keys
        assert m["variacao_cambial"] == -200000.0
        assert m["variacao_caixa"] == 4800000.0

    def test_dfc_extract_metrics_6_01_04_not_da(self):
        """[v1.11] Regression: 6.01.04 is NOT a D&A fallback.

        v1.2 had it as a "DFC_MD alt" fallback but real DFP shows it's
        "Pagamentos à Fornecedores" (11 rows), NOT D&A. v1.11 removed the
        fallback. Providing only 6.01.04 must yield da=None.
        """
        from skills.cvm.financials.fetchers import _extract_metrics
        vals = {"6.01.04": 2000.0}  # NO 6.01.01.02, NO 6.02.01.02
        m = _extract_metrics(vals)
        assert m["da"] is None  # 6.01.04 is "Pagamentos à Fornecedores", NOT D&A
