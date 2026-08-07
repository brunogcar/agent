"""Tests for skills/cvm/calculations/engines/receivables.py.

Snapshot engine (BPA codigo 1.01.03 -- Contas a Receber, point-in-time
balance, no TTM derivation). Mocks the internal _get_dfp_receivables +
_get_itr_receivables functions via monkeypatch -- no database needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines.bpa import receivables as receivables_engine


# -- Mock data ---------------------------------------------------------------

FAKE_DFP = {
    "2023-12-31": {"value": 45e9, "year": 2023},
    "2024-12-31": {"value": 50e9, "year": 2024},
}

FAKE_ITR = {
    "2024-03-31": {"value": 47e9, "meses": 3, "year": 2024},
    "2024-06-30": {"value": 48e9, "meses": 6, "year": 2024},
}


# -- receivables_at() tests --------------------------------------------------

class TestReceivablesAt:
    def test_basic_computation(self, monkeypatch):
        """receivables_at should return the most recent snapshot <= date."""
        monkeypatch.setattr(receivables_engine, "_get_dfp_receivables", lambda c: FAKE_DFP)
        monkeypatch.setattr(receivables_engine, "_get_itr_receivables", lambda c: FAKE_ITR)

        # At 2024-07-15 -> most recent snapshot is ITR 2024-06-30 (48e9)
        result = receivables_engine.receivables_at("PETR4", "2024-07-15")
        assert result == 48e9

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """Before any ITR snapshot, fall back to most recent DFP."""
        monkeypatch.setattr(receivables_engine, "_get_dfp_receivables", lambda c: FAKE_DFP)
        monkeypatch.setattr(receivables_engine, "_get_itr_receivables", lambda c: FAKE_ITR)

        # At 2024-01-15 -> most recent snapshot is DFP 2023-12-31 (45e9)
        result = receivables_engine.receivables_at("PETR4", "2024-01-15")
        assert result == 45e9

    def test_missing_company(self, monkeypatch):
        """Missing company (no data) -> None."""
        monkeypatch.setattr(receivables_engine, "_get_dfp_receivables", lambda c: {})
        monkeypatch.setattr(receivables_engine, "_get_itr_receivables", lambda c: {})

        assert receivables_engine.receivables_at("UNKNOWN", "2024-06-30") is None

    def test_no_snapshot_before_date(self, monkeypatch):
        """All snapshots after the requested date -> None."""
        monkeypatch.setattr(receivables_engine, "_get_dfp_receivables", lambda c: FAKE_DFP)
        monkeypatch.setattr(receivables_engine, "_get_itr_receivables", lambda c: FAKE_ITR)

        # 2020 is before any snapshot
        assert receivables_engine.receivables_at("PETR4", "2020-01-01") is None


# -- receivables_periods() tests ---------------------------------------------

class TestReceivablesPeriods:
    def test_periods(self, monkeypatch):
        """receivables_periods returns list of {date, receivables} sorted oldest-first."""
        monkeypatch.setattr(receivables_engine, "_get_dfp_receivables", lambda c: FAKE_DFP)
        monkeypatch.setattr(receivables_engine, "_get_itr_receivables", lambda c: FAKE_ITR)

        result = receivables_engine.receivables_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) == 4  # 2 DFP + 2 ITR (distinct dates)

        # Sorted oldest-first
        assert result[0]["date"] == "2023-12-31"
        assert result[-1]["date"] == "2024-12-31"

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "receivables" in entry
            assert isinstance(entry["receivables"], float)

    def test_periods_empty_when_no_data(self, monkeypatch):
        monkeypatch.setattr(receivables_engine, "_get_dfp_receivables", lambda c: {})
        monkeypatch.setattr(receivables_engine, "_get_itr_receivables", lambda c: {})

        assert receivables_engine.receivables_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestReceivablesRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "receivables" in ENGINES
        spec = ENGINES["receivables"]
        assert spec.name == "receivables"
        assert spec.category == "bpa"
        assert spec.quantity == "receivables"
        assert spec.at_fn is receivables_engine.receivables_at
        assert spec.periods_fn is receivables_engine.receivables_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query BPA codigo 1.01.03 (Contas a Receber)."""
        assert receivables_engine.CONTAS_A_RECEBER_CODE == "1.01.03"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "1.01.03" in ENGINES["receivables"].source
