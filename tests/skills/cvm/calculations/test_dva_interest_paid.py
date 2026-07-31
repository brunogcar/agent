"""Tests for skills/cvm/calculations/engines/dva_interest_paid.py.

Flow engine (DVA grupo='DVA', codigo 7.08.03 -- Remuneração do Capital de
Terceiros / interest paid to lenders, TTM derivation from DFP + ITR
cumulative). Mocks the internal _get_dfp_dva_interest_paid +
_get_itr_dva_interest_paid functions via monkeypatch -- no database needed.

Interest paid is typically NEGATIVE on the DVA (it's a wealth OUTFLOW to
lenders). The engine returns the raw value (sign preserved). These tests
use negative mock values to mirror the real DVA.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import dva_interest_paid as dva_ip_engine


# -- Mock data ---------------------------------------------------------------
# Mirror real DVA sign convention: interest paid is a NEGATIVE figure
# (wealth distributed to third-party capital providers / lenders).

FAKE_DFP = {
    "2023": {"value": -8e9, "date": "2023-12-31"},
}

FAKE_ITR = {
    "2024-03-31": {"value": -2.5e9, "meses": 3, "year": 2024},
    "2023-03-31": {"value": -1.8e9, "meses": 3, "year": 2023},
}


# -- dva_interest_paid_at() tests (TTM derivation) ---------------------------

class TestDvaInterestPaidAt:
    def test_basic_computation(self, monkeypatch):
        """dva_interest_paid_at should derive TTM via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = -8e9 - (-1.8e9) + (-2.5e9)
                          = -8.7e9
        """
        monkeypatch.setattr(dva_ip_engine, "_get_dfp_dva_interest_paid", lambda c: FAKE_DFP)
        monkeypatch.setattr(dva_ip_engine, "_get_itr_dva_interest_paid", lambda c: FAKE_ITR)

        result = dva_ip_engine.dva_interest_paid_at("PETR4", "2024-04-15")
        assert result == pytest.approx(-8.7e9, rel=1e-6)

    def test_missing_company(self, monkeypatch):
        """Missing company (no DVA data) -> None.

        DVA is optional-filing in CVM -- some companies don't produce it.
        The engine should return None gracefully when no data exists.
        """
        monkeypatch.setattr(dva_ip_engine, "_get_dfp_dva_interest_paid", lambda c: {})
        monkeypatch.setattr(dva_ip_engine, "_get_itr_dva_interest_paid", lambda c: {})

        assert dva_ip_engine.dva_interest_paid_at("UNKNOWN", "2024-06-30") is None

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        fake_dfp = {"2020": {"value": -5e9, "date": "2020-12-31"}}
        monkeypatch.setattr(dva_ip_engine, "_get_dfp_dva_interest_paid", lambda c: fake_dfp)
        monkeypatch.setattr(dva_ip_engine, "_get_itr_dva_interest_paid", lambda c: {})

        assert dva_ip_engine.dva_interest_paid_at("PETR4", "2021-01-15") == -5e9

    def test_no_prior_year_dfp_returns_none(self, monkeypatch):
        """No DFP for prior year -> can't derive TTM -> None."""
        fake_dfp = {}
        fake_itr = {
            "2024-03-31": {"value": -2.5e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(dva_ip_engine, "_get_dfp_dva_interest_paid", lambda c: fake_dfp)
        monkeypatch.setattr(dva_ip_engine, "_get_itr_dva_interest_paid", lambda c: fake_itr)

        assert dva_ip_engine.dva_interest_paid_at("PETR4", "2024-04-15") is None

    def test_ttm_at_exact_period_end(self, monkeypatch):
        """TTM at exact ITR period end date should use that ITR."""
        monkeypatch.setattr(dva_ip_engine, "_get_dfp_dva_interest_paid", lambda c: FAKE_DFP)
        monkeypatch.setattr(dva_ip_engine, "_get_itr_dva_interest_paid", lambda c: FAKE_ITR)

        result = dva_ip_engine.dva_interest_paid_at("PETR4", "2024-03-31")
        assert result == pytest.approx(-8.7e9, rel=1e-6)


# -- dva_interest_paid_periods() tests ---------------------------------------

class TestDvaInterestPaidPeriods:
    def test_periods(self, monkeypatch):
        """dva_interest_paid_periods returns list of {date, ttm_dva_interest}."""
        fake_dfp = {
            "2021": {"value": -3e9, "date": "2021-12-31"},
            "2022": {"value": -5e9, "date": "2022-12-31"},
            "2023": {"value": -8e9, "date": "2023-12-31"},
        }
        fake_itr = {
            "2022-03-31": {"value": -1.0e9, "meses": 3, "year": 2022},
            "2023-03-31": {"value": -1.8e9, "meses": 3, "year": 2023},
            "2024-03-31": {"value": -2.5e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(dva_ip_engine, "_get_dfp_dva_interest_paid", lambda c: fake_dfp)
        monkeypatch.setattr(dva_ip_engine, "_get_itr_dva_interest_paid", lambda c: fake_itr)

        result = dva_ip_engine.dva_interest_paid_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_dva_interest" in entry
            assert isinstance(entry["ttm_dva_interest"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))

    def test_periods_empty_when_no_data(self, monkeypatch):
        """No DVA data -> empty periods list (graceful degradation)."""
        monkeypatch.setattr(dva_ip_engine, "_get_dfp_dva_interest_paid", lambda c: {})
        monkeypatch.setattr(dva_ip_engine, "_get_itr_dva_interest_paid", lambda c: {})

        assert dva_ip_engine.dva_interest_paid_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestDvaInterestPaidRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "dva_interest_paid" in ENGINES
        spec = ENGINES["dva_interest_paid"]
        assert spec.name == "dva_interest_paid"
        assert spec.category == "dva"
        assert spec.quantity == "ttm_dva_interest"
        assert spec.at_fn is dva_ip_engine.dva_interest_paid_at
        assert spec.periods_fn is dva_ip_engine.dva_interest_paid_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DVA codigo 7.08.03 (Remuneração do Capital de Terceiros)."""
        assert dva_ip_engine.DVA_INTEREST_PAID_CODE == "7.08.03"

    def test_uses_new_chart_fallback_code(self):
        """Engine should also query the new-chart codigo 7.11.03 as a fallback."""
        assert dva_ip_engine.DVA_INTEREST_PAID_CODE_NEW == "7.11.03"

    def test_uses_grupo_like_filter(self):
        """Engine should NOT use a literal DVA_GRUPO variable (SQL uses LIKE).

        The grupo field stores the full Portuguese statement name (e.g.
        "DF Consolidado - Demonstração de Valor Adicionado"), not the
        short "DVA" abbreviation — so the SQL uses ``grupo LIKE '%Valor
        Adicionado%'`` and there is no DVA_GRUPO constant on the module.
        """
        assert not hasattr(dva_ip_engine, "DVA_GRUPO")

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "7.08.03" in ENGINES["dva_interest_paid"].source
        assert "7.11.03" in ENGINES["dva_interest_paid"].source  # new-chart fallback

    def test_source_mentions_grupo_dva(self):
        """Engine source string should mention the DVA grupo filter for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "Valor Adicionado" in ENGINES["dva_interest_paid"].source
