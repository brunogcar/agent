"""Tests for skills/cvm/calculations/engines/payables.py.

Snapshot engine (BPP codigo 2.01.01 -- Fornecedores, point-in-time balance,
no TTM derivation). Mocks the internal _get_dfp_payables +
_get_itr_payables functions via monkeypatch -- no database needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines.bpp import payables as payables_engine


# -- Mock data ---------------------------------------------------------------

FAKE_DFP = {
    "2023-12-31": {"value": 28e9, "year": 2023},
    "2024-12-31": {"value": 30e9, "year": 2024},
}

FAKE_ITR = {
    "2024-03-31": {"value": 27e9, "meses": 3, "year": 2024},
    "2024-06-30": {"value": 29e9, "meses": 6, "year": 2024},
}


# -- payables_at() tests -----------------------------------------------------

class TestPayablesAt:
    def test_basic_computation(self, monkeypatch):
        """payables_at should return the most recent snapshot <= date."""
        monkeypatch.setattr(payables_engine, "_get_dfp_payables", lambda c: FAKE_DFP)
        monkeypatch.setattr(payables_engine, "_get_itr_payables", lambda c: FAKE_ITR)

        # At 2024-07-15 -> most recent snapshot is ITR 2024-06-30 (29e9)
        result = payables_engine.payables_at("PETR4", "2024-07-15")
        assert result == 29e9

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """Before any ITR snapshot, fall back to most recent DFP."""
        monkeypatch.setattr(payables_engine, "_get_dfp_payables", lambda c: FAKE_DFP)
        monkeypatch.setattr(payables_engine, "_get_itr_payables", lambda c: FAKE_ITR)

        # At 2024-01-15 -> most recent snapshot is DFP 2023-12-31 (28e9)
        result = payables_engine.payables_at("PETR4", "2024-01-15")
        assert result == 28e9

    def test_missing_company(self, monkeypatch):
        """Missing company (no data) -> None."""
        monkeypatch.setattr(payables_engine, "_get_dfp_payables", lambda c: {})
        monkeypatch.setattr(payables_engine, "_get_itr_payables", lambda c: {})

        assert payables_engine.payables_at("UNKNOWN", "2024-06-30") is None

    def test_no_snapshot_before_date(self, monkeypatch):
        """All snapshots after the requested date -> None."""
        monkeypatch.setattr(payables_engine, "_get_dfp_payables", lambda c: FAKE_DFP)
        monkeypatch.setattr(payables_engine, "_get_itr_payables", lambda c: FAKE_ITR)

        # 2020 is before any snapshot
        assert payables_engine.payables_at("PETR4", "2020-01-01") is None


# -- payables_periods() tests ------------------------------------------------

class TestPayablesPeriods:
    def test_periods(self, monkeypatch):
        """payables_periods returns list of {date, payables} sorted oldest-first."""
        monkeypatch.setattr(payables_engine, "_get_dfp_payables", lambda c: FAKE_DFP)
        monkeypatch.setattr(payables_engine, "_get_itr_payables", lambda c: FAKE_ITR)

        result = payables_engine.payables_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) == 4  # 2 DFP + 2 ITR (distinct dates)

        # Sorted oldest-first
        assert result[0]["date"] == "2023-12-31"
        assert result[-1]["date"] == "2024-12-31"

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "payables" in entry
            assert isinstance(entry["payables"], float)

    def test_periods_empty_when_no_data(self, monkeypatch):
        monkeypatch.setattr(payables_engine, "_get_dfp_payables", lambda c: {})
        monkeypatch.setattr(payables_engine, "_get_itr_payables", lambda c: {})

        assert payables_engine.payables_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestPayablesRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "payables" in ENGINES
        spec = ENGINES["payables"]
        assert spec.name == "payables"
        assert spec.category == "bpp"
        assert spec.quantity == "payables"
        assert spec.at_fn is payables_engine.payables_at
        assert spec.periods_fn is payables_engine.payables_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query BPP codigo 2.01.01 (Fornecedores)."""
        assert payables_engine.FORNECEDORES_CODE == "2.01.01"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "2.01.01" in ENGINES["payables"].source
