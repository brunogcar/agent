"""Tests for skills/cvm/calculations/engines/cogs.py.

Flow engine (DRE codigo 3.02 -- Custo dos Bens Vendidos / COGS, TTM
derivation from DFP + ITR cumulative). Mocks the internal _get_dfp_cogs
+ _get_itr_cogs functions via monkeypatch -- no database needed.

COGS is typically NEGATIVE on the DRE (it's a cost/deduction). The engine
returns the raw value (sign preserved). These tests use negative mock
values to mirror the real DRE.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import cogs as cogs_engine


# -- Mock data ---------------------------------------------------------------
# Mirror real DRE sign convention: COGS is a NEGATIVE figure.

FAKE_DFP = {
    "2023": {"value": -150e9, "date": "2023-12-31"},
}

FAKE_ITR = {
    "2024-03-31": {"value": -40e9, "meses": 3, "year": 2024},
    "2023-03-31": {"value": -35e9, "meses": 3, "year": 2023},
}


# -- cogs_at() tests (TTM derivation) ----------------------------------------

class TestCogsAt:
    def test_basic_computation(self, monkeypatch):
        """cogs_at should derive TTM COGS via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = -150e9 - (-35e9) + (-40e9)
                          = -155e9
        """
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: FAKE_DFP)
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: FAKE_ITR)

        result = cogs_engine.cogs_at("PETR4", "2024-04-15")
        assert result == pytest.approx(-155e9, rel=1e-6)

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: FAKE_DFP)
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: FAKE_ITR)

        # At 2024-01-15 -> no ITR before this date (earliest ITR is 2023-03-31)
        # Actually 2023-03-31 IS before 2024-01-15. Let me use an earlier date.
        # At 2022-01-15 -> no ITR before this date (earliest ITR is 2023-03-31)
        # But DFP "2023" date is "2023-12-31" which is also after 2022-01-15.
        # Use FAKE_DFP with an earlier year.
        fake_dfp = {"2020": {"value": -100e9, "date": "2020-12-31"}}
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: fake_dfp)
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: {})  # no ITR

        assert cogs_engine.cogs_at("PETR4", "2021-01-15") == -100e9

    def test_missing_company(self, monkeypatch):
        """Missing company (no data) -> None."""
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: {})
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: {})

        assert cogs_engine.cogs_at("UNKNOWN", "2024-06-30") is None

    def test_no_prior_year_dfp_returns_none(self, monkeypatch):
        """No DFP for prior year -> can't derive TTM -> None.

        The current ITR is 2024-Q1 but there's no DFP for 2023 to subtract
        from.
        """
        fake_dfp = {}  # no DFP at all
        fake_itr = {
            "2024-03-31": {"value": -40e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: fake_dfp)
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: fake_itr)

        assert cogs_engine.cogs_at("PETR4", "2024-04-15") is None

    def test_no_itr_before_date_uses_dfp(self, monkeypatch):
        """No ITR before requested date -> fall back to DFP annual."""
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: FAKE_DFP)
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: FAKE_ITR)

        # At 2022-06-15 -> no ITR before this date (earliest ITR is 2023-03-31)
        # DFP "2023" date "2023-12-31" is also after 2022-06-15.
        # So with FAKE_DFP only, there is NO DFP <= 2022-06-15. Should return None.
        assert cogs_engine.cogs_at("PETR4", "2022-06-15") is None

    def test_ttm_at_exact_period_end(self, monkeypatch):
        """TTM at exact ITR period end date should use that ITR."""
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: FAKE_DFP)
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: FAKE_ITR)

        # At 2024-03-31 -> most recent ITR <= date is 2024-03-31 itself
        result = cogs_engine.cogs_at("PETR4", "2024-03-31")
        assert result == pytest.approx(-155e9, rel=1e-6)


# -- cogs_periods() tests ----------------------------------------------------

class TestCogsPeriods:
    def test_periods(self, monkeypatch):
        """cogs_periods returns list of {date, ttm_cogs} sorted oldest-first."""
        # Use richer mock data so we get multiple TTM periods + a DFP-only
        # entry from a year before the first ITR.
        fake_dfp = {
            "2021": {"value": -100e9, "date": "2021-12-31"},
            "2022": {"value": -120e9, "date": "2022-12-31"},
            "2023": {"value": -150e9, "date": "2023-12-31"},
        }
        fake_itr = {
            "2022-03-31": {"value": -30e9, "meses": 3, "year": 2022},
            "2023-03-31": {"value": -35e9, "meses": 3, "year": 2023},
            "2024-03-31": {"value": -40e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: fake_dfp)
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: fake_itr)

        result = cogs_engine.cogs_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_cogs" in entry
            assert isinstance(entry["ttm_cogs"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))

    def test_periods_empty_when_no_data(self, monkeypatch):
        monkeypatch.setattr(cogs_engine, "_get_dfp_cogs", lambda c: {})
        monkeypatch.setattr(cogs_engine, "_get_itr_cogs", lambda c: {})

        assert cogs_engine.cogs_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestCogsRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "cogs" in ENGINES
        spec = ENGINES["cogs"]
        assert spec.name == "cogs"
        assert spec.category == "dre"
        assert spec.quantity == "ttm_cogs"
        assert spec.at_fn is cogs_engine.cogs_at
        assert spec.periods_fn is cogs_engine.cogs_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DRE codigo 3.02 (Custo dos Bens Vendidos)."""
        assert cogs_engine.COGS_CODE == "3.02"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "3.02" in ENGINES["cogs"].source
