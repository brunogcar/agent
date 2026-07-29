"""Tests for skills/cvm/calculations/engines/interest_paid.py.

Flow engine (DVA grupo='DVA', codigo 8.3 -- Remuneração do Capital de
Terceiros / interest paid to lenders, TTM derivation from DFP + ITR
cumulative). Mocks the internal _get_dfp_interest_paid +
_get_itr_interest_paid functions via monkeypatch -- no database needed.

Interest paid is typically NEGATIVE on the DVA (it's a wealth OUTFLOW to
lenders). The engine returns the raw value (sign preserved). These tests
use negative mock values to mirror the real DVA.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import interest_paid as ip_engine


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


# -- interest_paid_at() tests (TTM derivation) --------------------------------

class TestInterestPaidAt:
    def test_basic_computation(self, monkeypatch):
        """interest_paid_at should derive TTM via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = -8e9 - (-1.8e9) + (-2.5e9)
                          = -8.7e9
        """
        monkeypatch.setattr(ip_engine, "_get_dfp_interest_paid", lambda c: FAKE_DFP)
        monkeypatch.setattr(ip_engine, "_get_itr_interest_paid", lambda c: FAKE_ITR)

        result = ip_engine.interest_paid_at("PETR4", "2024-04-15")
        assert result == pytest.approx(-8.7e9, rel=1e-6)

    def test_missing_company(self, monkeypatch):
        """Missing company (no DVA data) -> None.

        DVA is optional-filing in CVM -- some companies don't produce it.
        The engine should return None gracefully when no data exists.
        """
        monkeypatch.setattr(ip_engine, "_get_dfp_interest_paid", lambda c: {})
        monkeypatch.setattr(ip_engine, "_get_itr_interest_paid", lambda c: {})

        assert ip_engine.interest_paid_at("UNKNOWN", "2024-06-30") is None

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        fake_dfp = {"2020": {"value": -5e9, "date": "2020-12-31"}}
        monkeypatch.setattr(ip_engine, "_get_dfp_interest_paid", lambda c: fake_dfp)
        monkeypatch.setattr(ip_engine, "_get_itr_interest_paid", lambda c: {})

        assert ip_engine.interest_paid_at("PETR4", "2021-01-15") == -5e9

    def test_no_prior_year_dfp_returns_none(self, monkeypatch):
        """No DFP for prior year -> can't derive TTM -> None."""
        fake_dfp = {}
        fake_itr = {
            "2024-03-31": {"value": -2.5e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(ip_engine, "_get_dfp_interest_paid", lambda c: fake_dfp)
        monkeypatch.setattr(ip_engine, "_get_itr_interest_paid", lambda c: fake_itr)

        assert ip_engine.interest_paid_at("PETR4", "2024-04-15") is None

    def test_ttm_at_exact_period_end(self, monkeypatch):
        """TTM at exact ITR period end date should use that ITR."""
        monkeypatch.setattr(ip_engine, "_get_dfp_interest_paid", lambda c: FAKE_DFP)
        monkeypatch.setattr(ip_engine, "_get_itr_interest_paid", lambda c: FAKE_ITR)

        result = ip_engine.interest_paid_at("PETR4", "2024-03-31")
        assert result == pytest.approx(-8.7e9, rel=1e-6)


# -- interest_paid_periods() tests --------------------------------------------

class TestInterestPaidPeriods:
    def test_periods(self, monkeypatch):
        """interest_paid_periods returns list of {date, ttm_interest_paid}."""
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
        monkeypatch.setattr(ip_engine, "_get_dfp_interest_paid", lambda c: fake_dfp)
        monkeypatch.setattr(ip_engine, "_get_itr_interest_paid", lambda c: fake_itr)

        result = ip_engine.interest_paid_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_interest_paid" in entry
            assert isinstance(entry["ttm_interest_paid"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))

    def test_periods_empty_when_no_data(self, monkeypatch):
        """No DVA data -> empty periods list (graceful degradation)."""
        monkeypatch.setattr(ip_engine, "_get_dfp_interest_paid", lambda c: {})
        monkeypatch.setattr(ip_engine, "_get_itr_interest_paid", lambda c: {})

        assert ip_engine.interest_paid_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestInterestPaidRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "interest_paid" in ENGINES
        spec = ENGINES["interest_paid"]
        assert spec.name == "interest_paid"
        assert spec.category == "dva"
        assert spec.quantity == "ttm_interest_paid"
        assert spec.at_fn is ip_engine.interest_paid_at
        assert spec.periods_fn is ip_engine.interest_paid_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DVA codigo 8.3 (Remuneração do Capital de Terceiros)."""
        assert ip_engine.INTEREST_PAID_CODE == "8.3"

    def test_uses_correct_grupo(self):
        """Engine should filter by grupo='DVA' (DVA codes are scoped to the DVA group)."""
        assert ip_engine.DVA_GRUPO == "DVA"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "8.3" in ENGINES["interest_paid"].source

    def test_source_mentions_grupo_dva(self):
        """Engine source string should mention grupo='DVA' for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "DVA" in ENGINES["interest_paid"].source
