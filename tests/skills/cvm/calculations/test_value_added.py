"""Tests for skills/cvm/calculations/engines/value_added.py.

Flow engine (DVA grupo='DVA', codigo 7 -- Valor Adicionado Total a
Distribuir / total wealth created by the company, TTM derivation from
DFP + ITR cumulative). Mocks the internal _get_dfp_value_added +
_get_itr_value_added functions via monkeypatch -- no database needed.

Total value added is typically POSITIVE on the DVA (it's the wealth
created by the company, available for distribution to stakeholders).
The engine returns the raw value (sign preserved). These tests use
positive mock values to mirror the real DVA.

DVA 7 should conceptually equal the sum of the distribution-side lines:
8.1 (personnel) + 8.2 (government/tax) + 8.3 (lenders/interest) +
8.4 (shareholders/dividends+earnings).
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines.dva import value_added as va_engine


# -- Mock data ---------------------------------------------------------------
# Mirror real DVA sign convention: total value added is a POSITIVE figure
# (wealth created and available for distribution to stakeholders).

FAKE_DFP = {
    "2023": {"value": 250e9, "date": "2023-12-31"},
}

FAKE_ITR = {
    "2024-03-31": {"value": 70e9, "meses": 3, "year": 2024},
    "2023-03-31": {"value": 60e9, "meses": 3, "year": 2023},
}


# -- value_added_at() tests (TTM derivation) ----------------------------------

class TestValueAddedAt:
    def test_basic_computation(self, monkeypatch):
        """value_added_at should derive TTM via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = 250e9 - 60e9 + 70e9
                          = 260e9
        """
        monkeypatch.setattr(va_engine, "_get_dfp_value_added", lambda c: FAKE_DFP)
        monkeypatch.setattr(va_engine, "_get_itr_value_added", lambda c: FAKE_ITR)

        result = va_engine.value_added_at("PETR4", "2024-04-15")
        assert result == pytest.approx(260e9, rel=1e-6)

    def test_missing_company(self, monkeypatch):
        """Missing company (no DVA data) -> None.

        DVA is optional-filing in CVM -- some companies don't produce it.
        The engine should return None gracefully when no data exists.
        """
        monkeypatch.setattr(va_engine, "_get_dfp_value_added", lambda c: {})
        monkeypatch.setattr(va_engine, "_get_itr_value_added", lambda c: {})

        assert va_engine.value_added_at("UNKNOWN", "2024-06-30") is None

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        fake_dfp = {"2020": {"value": 180e9, "date": "2020-12-31"}}
        monkeypatch.setattr(va_engine, "_get_dfp_value_added", lambda c: fake_dfp)
        monkeypatch.setattr(va_engine, "_get_itr_value_added", lambda c: {})

        assert va_engine.value_added_at("PETR4", "2021-01-15") == 180e9

    def test_no_prior_year_dfp_returns_none(self, monkeypatch):
        """No DFP for prior year -> can't derive TTM -> None."""
        fake_dfp = {}
        fake_itr = {
            "2024-03-31": {"value": 70e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(va_engine, "_get_dfp_value_added", lambda c: fake_dfp)
        monkeypatch.setattr(va_engine, "_get_itr_value_added", lambda c: fake_itr)

        assert va_engine.value_added_at("PETR4", "2024-04-15") is None

    def test_ttm_at_exact_period_end(self, monkeypatch):
        """TTM at exact ITR period end date should use that ITR."""
        monkeypatch.setattr(va_engine, "_get_dfp_value_added", lambda c: FAKE_DFP)
        monkeypatch.setattr(va_engine, "_get_itr_value_added", lambda c: FAKE_ITR)

        result = va_engine.value_added_at("PETR4", "2024-03-31")
        assert result == pytest.approx(260e9, rel=1e-6)


# -- value_added_periods() tests ----------------------------------------------

class TestValueAddedPeriods:
    def test_periods(self, monkeypatch):
        """value_added_periods returns list of {date, ttm_value_added}."""
        fake_dfp = {
            "2021": {"value": 150e9, "date": "2021-12-31"},
            "2022": {"value": 200e9, "date": "2022-12-31"},
            "2023": {"value": 250e9, "date": "2023-12-31"},
        }
        fake_itr = {
            "2022-03-31": {"value": 45e9, "meses": 3, "year": 2022},
            "2023-03-31": {"value": 60e9, "meses": 3, "year": 2023},
            "2024-03-31": {"value": 70e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(va_engine, "_get_dfp_value_added", lambda c: fake_dfp)
        monkeypatch.setattr(va_engine, "_get_itr_value_added", lambda c: fake_itr)

        result = va_engine.value_added_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_value_added" in entry
            assert isinstance(entry["ttm_value_added"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))

    def test_periods_empty_when_no_data(self, monkeypatch):
        """No DVA data -> empty periods list (graceful degradation)."""
        monkeypatch.setattr(va_engine, "_get_dfp_value_added", lambda c: {})
        monkeypatch.setattr(va_engine, "_get_itr_value_added", lambda c: {})

        assert va_engine.value_added_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestValueAddedRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "value_added" in ENGINES
        spec = ENGINES["value_added"]
        assert spec.name == "value_added"
        assert spec.category == "dva"
        assert spec.quantity == "ttm_value_added"
        assert spec.at_fn is va_engine.value_added_at
        assert spec.periods_fn is va_engine.value_added_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DVA codigo 7.08 (Valor Adicionado Total a Distribuir)."""
        assert va_engine.VALUE_ADDED_CODE == "7.08"

    def test_uses_new_chart_fallback_code(self):
        """Engine should also query the new-chart codigo 7.10 as a fallback."""
        assert va_engine.VALUE_ADDED_CODE_NEW == "7.10"

    def test_uses_grupo_like_filter(self):
        """Engine should NOT use a literal DVA_GRUPO variable (SQL uses LIKE).

        The grupo field stores the full Portuguese statement name (e.g.
        "DF Consolidado - Demonstração de Valor Adicionado"), not the
        short "DVA" abbreviation — so the SQL uses ``grupo LIKE '%Valor
        Adicionado%'`` and there is no DVA_GRUPO constant on the module.
        """
        assert not hasattr(va_engine, "DVA_GRUPO")

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "7.08" in ENGINES["value_added"].source
        assert "7.10" in ENGINES["value_added"].source  # new-chart fallback

    def test_source_mentions_grupo_dva(self):
        """Engine source string should mention the DVA grupo filter for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "Valor Adicionado" in ENGINES["value_added"].source
