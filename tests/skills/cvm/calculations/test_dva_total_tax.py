"""Tests for skills/cvm/calculations/engines/dva_total_tax.py.

Flow engine (DVA grupo='DVA', codigo 7.08.02 -- Impostos, Taxas e Contribuições
/ total tax burden, TTM derivation from DFP + ITR cumulative). Mocks the
internal _get_dfp_dva_total_tax + _get_itr_dva_total_tax functions via
monkeypatch -- no database needed.

Total tax burden is typically NEGATIVE on the DVA (it's a wealth OUTFLOW
to government). The engine returns the raw value (sign preserved). These
tests use negative mock values to mirror the real DVA.

DVA 8.2 is broader than DRE 3.08 (income tax only) -- it also captures
indirect taxes like PIS/COFINS/ICMS/IPI/ISS.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import dva_total_tax as dva_tt_engine


# -- Mock data ---------------------------------------------------------------
# Mirror real DVA sign convention: total tax burden is a NEGATIVE figure
# (wealth distributed to government -- income tax + indirect taxes).

FAKE_DFP = {
    "2023": {"value": -90e9, "date": "2023-12-31"},
}

FAKE_ITR = {
    "2024-03-31": {"value": -25e9, "meses": 3, "year": 2024},
    "2023-03-31": {"value": -22e9, "meses": 3, "year": 2023},
}


# -- dva_total_tax_at() tests (TTM derivation) -------------------------------

class TestDvaTotalTaxAt:
    def test_basic_computation(self, monkeypatch):
        """dva_total_tax_at should derive TTM via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = -90e9 - (-22e9) + (-25e9)
                          = -93e9
        """
        monkeypatch.setattr(dva_tt_engine, "_get_dfp_dva_total_tax", lambda c: FAKE_DFP)
        monkeypatch.setattr(dva_tt_engine, "_get_itr_dva_total_tax", lambda c: FAKE_ITR)

        result = dva_tt_engine.dva_total_tax_at("PETR4", "2024-04-15")
        assert result == pytest.approx(-93e9, rel=1e-6)

    def test_missing_company(self, monkeypatch):
        """Missing company (no DVA data) -> None.

        DVA is optional-filing in CVM -- some companies don't produce it.
        The engine should return None gracefully when no data exists.
        """
        monkeypatch.setattr(dva_tt_engine, "_get_dfp_dva_total_tax", lambda c: {})
        monkeypatch.setattr(dva_tt_engine, "_get_itr_dva_total_tax", lambda c: {})

        assert dva_tt_engine.dva_total_tax_at("UNKNOWN", "2024-06-30") is None

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        fake_dfp = {"2020": {"value": -60e9, "date": "2020-12-31"}}
        monkeypatch.setattr(dva_tt_engine, "_get_dfp_dva_total_tax", lambda c: fake_dfp)
        monkeypatch.setattr(dva_tt_engine, "_get_itr_dva_total_tax", lambda c: {})

        assert dva_tt_engine.dva_total_tax_at("PETR4", "2021-01-15") == -60e9

    def test_no_prior_year_dfp_returns_none(self, monkeypatch):
        """No DFP for prior year -> can't derive TTM -> None."""
        fake_dfp = {}
        fake_itr = {
            "2024-03-31": {"value": -25e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(dva_tt_engine, "_get_dfp_dva_total_tax", lambda c: fake_dfp)
        monkeypatch.setattr(dva_tt_engine, "_get_itr_dva_total_tax", lambda c: fake_itr)

        assert dva_tt_engine.dva_total_tax_at("PETR4", "2024-04-15") is None

    def test_ttm_at_exact_period_end(self, monkeypatch):
        """TTM at exact ITR period end date should use that ITR."""
        monkeypatch.setattr(dva_tt_engine, "_get_dfp_dva_total_tax", lambda c: FAKE_DFP)
        monkeypatch.setattr(dva_tt_engine, "_get_itr_dva_total_tax", lambda c: FAKE_ITR)

        result = dva_tt_engine.dva_total_tax_at("PETR4", "2024-03-31")
        assert result == pytest.approx(-93e9, rel=1e-6)


# -- dva_total_tax_periods() tests -------------------------------------------

class TestDvaTotalTaxPeriods:
    def test_periods(self, monkeypatch):
        """dva_total_tax_periods returns list of {date, ttm_dva_tax}."""
        fake_dfp = {
            "2021": {"value": -50e9, "date": "2021-12-31"},
            "2022": {"value": -70e9, "date": "2022-12-31"},
            "2023": {"value": -90e9, "date": "2023-12-31"},
        }
        fake_itr = {
            "2022-03-31": {"value": -15e9, "meses": 3, "year": 2022},
            "2023-03-31": {"value": -22e9, "meses": 3, "year": 2023},
            "2024-03-31": {"value": -25e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(dva_tt_engine, "_get_dfp_dva_total_tax", lambda c: fake_dfp)
        monkeypatch.setattr(dva_tt_engine, "_get_itr_dva_total_tax", lambda c: fake_itr)

        result = dva_tt_engine.dva_total_tax_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_dva_tax" in entry
            assert isinstance(entry["ttm_dva_tax"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))

    def test_periods_empty_when_no_data(self, monkeypatch):
        """No DVA data -> empty periods list (graceful degradation)."""
        monkeypatch.setattr(dva_tt_engine, "_get_dfp_dva_total_tax", lambda c: {})
        monkeypatch.setattr(dva_tt_engine, "_get_itr_dva_total_tax", lambda c: {})

        assert dva_tt_engine.dva_total_tax_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestDvaTotalTaxRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "dva_total_tax" in ENGINES
        spec = ENGINES["dva_total_tax"]
        assert spec.name == "dva_total_tax"
        assert spec.category == "dva"
        assert spec.quantity == "ttm_dva_tax"
        assert spec.at_fn is dva_tt_engine.dva_total_tax_at
        assert spec.periods_fn is dva_tt_engine.dva_total_tax_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DVA codigo 7.08.02 (Impostos, Taxas e Contribuições)."""
        assert dva_tt_engine.DVA_TOTAL_TAX_CODE == "7.08.02"

    def test_uses_new_chart_fallback_code(self):
        """Engine should also query the new-chart codigo 7.11.02 as a fallback."""
        assert dva_tt_engine.DVA_TOTAL_TAX_CODE_NEW == "7.11.02"

    def test_uses_grupo_like_filter(self):
        """Engine should NOT use a literal DVA_GRUPO variable (SQL uses LIKE).

        The grupo field stores the full Portuguese statement name (e.g.
        "DF Consolidado - Demonstração de Valor Adicionado"), not the
        short "DVA" abbreviation — so the SQL uses ``grupo LIKE '%Valor
        Adicionado%'`` and there is no DVA_GRUPO constant on the module.
        """
        assert not hasattr(dva_tt_engine, "DVA_GRUPO")

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "7.08.02" in ENGINES["dva_total_tax"].source
        assert "7.11.02" in ENGINES["dva_total_tax"].source  # new-chart fallback

    def test_source_mentions_grupo_dva(self):
        """Engine source string should mention the DVA grupo filter for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "Valor Adicionado" in ENGINES["dva_total_tax"].source
