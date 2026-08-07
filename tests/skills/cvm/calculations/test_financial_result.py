"""Tests for skills/cvm/calculations/engines/financial_result.py.

Flow engine (DRE codigo 3.06 -- Resultado Financeiro, TTM derivation from
DFP + ITR cumulative). Mocks the internal _get_dfp_financial_result +
_get_itr_financial_result functions via monkeypatch -- no database needed.

Financial Result = financial income - financial expenses (NET figure).
Can be positive (net income) or negative (net expense). The engine
returns the raw value (sign preserved). These tests use negative mock
values to mirror the typical case (large companies carry net financial
expense due to interest on debt).
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines.dre import financial_result as fr_engine


# -- Mock data ---------------------------------------------------------------
# Net financial EXPENSE: financial income - financial expense < 0.

FAKE_DFP = {
    "2023": {"value": -5e9, "date": "2023-12-31"},
}

FAKE_ITR = {
    "2024-03-31": {"value": -1.5e9, "meses": 3, "year": 2024},
    "2023-03-31": {"value": -1.0e9, "meses": 3, "year": 2023},
}


# -- financial_result_at() tests (TTM derivation) ----------------------------

class TestFinancialResultAt:
    def test_basic_computation(self, monkeypatch):
        """financial_result_at should derive TTM via DFP - ITR_prior + ITR_current.

        TTM at 2024-04-15 = DFP_2023 - ITR_2023_Q1 + ITR_2024_Q1
                          = -5e9 - (-1e9) + (-1.5e9)
                          = -5.5e9
        """
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: FAKE_DFP)
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: FAKE_ITR)

        result = fr_engine.financial_result_at("PETR4", "2024-04-15")
        assert result == pytest.approx(-5.5e9, rel=1e-6)

    def test_positive_net_income(self, monkeypatch):
        """Financial result can be positive (net financial income)."""
        fake_dfp = {"2023": {"value": 2e9, "date": "2023-12-31"}}
        fake_itr = {
            "2024-03-31": {"value": 0.6e9, "meses": 3, "year": 2024},
            "2023-03-31": {"value": 0.5e9, "meses": 3, "year": 2023},
        }
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: fake_dfp)
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: fake_itr)

        # TTM = 2e9 - 0.5e9 + 0.6e9 = 2.1e9
        result = fr_engine.financial_result_at("PETR4", "2024-04-15")
        assert result == pytest.approx(2.1e9, rel=1e-6)

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """No ITR before date -> fall back to DFP annual."""
        fake_dfp = {"2020": {"value": -3e9, "date": "2020-12-31"}}
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: fake_dfp)
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: {})

        assert fr_engine.financial_result_at("PETR4", "2021-01-15") == -3e9

    def test_missing_company(self, monkeypatch):
        """Missing company (no data) -> None."""
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: {})
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: {})

        assert fr_engine.financial_result_at("UNKNOWN", "2024-06-30") is None

    def test_no_prior_year_dfp_returns_none(self, monkeypatch):
        """No DFP for prior year -> can't derive TTM -> None."""
        fake_dfp = {}
        fake_itr = {
            "2024-03-31": {"value": -1.5e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: fake_dfp)
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: fake_itr)

        assert fr_engine.financial_result_at("PETR4", "2024-04-15") is None

    def test_ttm_at_exact_period_end(self, monkeypatch):
        """TTM at exact ITR period end date should use that ITR."""
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: FAKE_DFP)
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: FAKE_ITR)

        result = fr_engine.financial_result_at("PETR4", "2024-03-31")
        assert result == pytest.approx(-5.5e9, rel=1e-6)


# -- financial_result_periods() tests ----------------------------------------

class TestFinancialResultPeriods:
    def test_periods(self, monkeypatch):
        """financial_result_periods returns list of {date, ttm_financial_result}."""
        fake_dfp = {
            "2021": {"value": -2e9, "date": "2021-12-31"},
            "2022": {"value": -3e9, "date": "2022-12-31"},
            "2023": {"value": -5e9, "date": "2023-12-31"},
        }
        fake_itr = {
            "2022-03-31": {"value": -0.5e9, "meses": 3, "year": 2022},
            "2023-03-31": {"value": -1.0e9, "meses": 3, "year": 2023},
            "2024-03-31": {"value": -1.5e9, "meses": 3, "year": 2024},
        }
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: fake_dfp)
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: fake_itr)

        result = fr_engine.financial_result_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) >= 1

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ttm_financial_result" in entry
            assert isinstance(entry["ttm_financial_result"], float)

        # Sorted oldest-first
        dates = [e["date"] for e in result]
        assert dates == sorted(dates)

        # Deduplicated
        assert len(dates) == len(set(dates))

    def test_periods_empty_when_no_data(self, monkeypatch):
        monkeypatch.setattr(fr_engine, "_get_dfp_financial_result", lambda c: {})
        monkeypatch.setattr(fr_engine, "_get_itr_financial_result", lambda c: {})

        assert fr_engine.financial_result_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestFinancialResultRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "financial_result" in ENGINES
        spec = ENGINES["financial_result"]
        assert spec.name == "financial_result"
        assert spec.category == "dre"
        assert spec.quantity == "ttm_financial_result"
        assert spec.at_fn is fr_engine.financial_result_at
        assert spec.periods_fn is fr_engine.financial_result_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query DRE codigo 3.06 (Resultado Financeiro)."""
        assert fr_engine.RESULTADO_FINANCEIRO_CODE == "3.06"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "3.06" in ENGINES["financial_result"].source
