"""Tests for skills/cvm/calculations/engines/dividends_paid.py.

Flow engine (DVA grupo='DVA', codigo 8.4 -- Remuneração do Capital
Próprio / dividends distributed to shareholders, TTM derivation from
DFP + ITR cumulative). Mocks the internal _get_dfp_dividends_paid +
_get_itr_dividends_paid functions via monkeypatch -- no database needed.

Dividends paid is typically NEGATIVE on the DVA (it's a wealth OUTFLOW
to shareholders). The engine returns the raw value (sign preserved).
These tests use negative mock values to mirror the real DVA.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import dividends_paid as dp_engine


# -- Mock data ---------------------------------------------------------------
# Mirror real DVA sign convention: dividends paid is a NEGATIVE figure
# (wealth distributed to own-capital providers / shareholders).

FAKE_DFP = {
    "2023": {"value": -1.5e10, "date": "2023-12-31"},
}

FAKE_ITR = {
    "2024-03-31": {"value": -4.0e9, "meses": 3, "year": 2024},
    "2023-03-31": {"value": -3.0e9, "meses": 3, "year": 2023},
}


# -- dividends_paid_at() tests (TTM derivation) -------------------------------

class TestDividendsPaidAt:
    def test_basic_computation(self, monkeypatch):
        """dividends_paid_at should derive TTM via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = -1.5e10 - (-3.0e9) + (-4.0e9)
                          = -1.6e10
        """
        monkeypatch.setattr(dp_engine, "_get_dfp_dividends_paid", lambda c: FAKE_DFP)
        monkeypatch.setattr(dp_engine, "_get_itr_dividends_paid", lambda c: FAKE_ITR)

        result = dp_engine.dividends_paid_at("PETR4", "2024-04-15")
        assert result == pytest.approx(-1.6e10, rel=1e-6)

    def test_missing_company(self, monkeypatch):
        """Missing company (no DVA data) -> None.

        DVA is optional-filing in CVM -- some companies don't produce it.
        The engine should return None gracefully when no data exists.
        """
        monkeypatch.setattr(dp_engine, "_get_dfp_dividends_paid", lambda c: {})
        monkeypatch.setattr(dp_engine, "_get_itr_dividends_paid", lambda c: {})

        assert dp_engine.dividends_paid_at("UNKNOWN", "2024-06-30") is None


# -- dividends_paid_periods() tests -------------------------------------------

class TestDividendsPaidPeriods:
    def test_periods(self, monkeypatch):
        """dividends_paid_periods returns list of {date, ttm_dividends_paid}."""
        fake_dfp = {
            "2021": {"value": -6e9, "date": "2021-12-31"},
            "2022": {"value": -9e9, "date": "2022-12-31"},
            "2023": {"value": -1.5e10, "date": "2023-12-31"},
        }
        fake_itr = {
            "2022-03-31": {"value": -1.5e9, "meses": 3, "year": 2022},
            "2023-03-31": {"value": -3.0e9, "meses": 3, "year": 2023},
            "2024-03-31": {"value": -4.0e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(dp_engine, "_get_dfp_dividends_paid", lambda c: fake_dfp)
        monkeypatch.setattr(dp_engine, "_get_itr_dividends_paid", lambda c: fake_itr)

        result = dp_engine.dividends_paid_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_dividends_paid" in entry
            assert isinstance(entry["ttm_dividends_paid"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))


# -- Registry tests ----------------------------------------------------------

class TestDividendsPaidRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "dividends_paid" in ENGINES
        spec = ENGINES["dividends_paid"]
        assert spec.name == "dividends_paid"
        assert spec.category == "dva"
        assert spec.quantity == "ttm_dividends_paid"
        assert spec.at_fn is dp_engine.dividends_paid_at
        assert spec.periods_fn is dp_engine.dividends_paid_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DVA codigo 7.08.04 (Remuneração do Capital Próprio)."""
        assert dp_engine.DIVIDENDS_PAID_CODE == "7.08.04"

    def test_uses_new_chart_fallback_code(self):
        """Engine should also query the new-chart codigo 7.11.04 as a fallback."""
        assert dp_engine.DIVIDENDS_PAID_CODE_NEW == "7.11.04"

    def test_uses_grupo_like_filter(self):
        """Engine should NOT use a literal DVA_GRUPO variable (SQL uses LIKE).

        The grupo field stores the full Portuguese statement name (e.g.
        "DF Consolidado - Demonstração de Valor Adicionado"), not the
        short "DVA" abbreviation — so the SQL uses ``grupo LIKE '%Valor
        Adicionado%'`` and there is no DVA_GRUPO constant on the module.
        """
        assert not hasattr(dp_engine, "DVA_GRUPO")
