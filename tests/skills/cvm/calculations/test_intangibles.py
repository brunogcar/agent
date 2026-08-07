"""Tests for skills/cvm/calculations/engines/intangibles.py.

Snapshot engine (BPA codigo 1.02.04 -- Intangível, point-in-time balance,
no TTM derivation). Mocks the internal _get_dfp_intangibles +
_get_itr_intangibles functions via monkeypatch -- no database needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines.bpa import intangibles as intangibles_engine


# -- Mock data ---------------------------------------------------------------

FAKE_DFP = {
    "2023-12-31": {"value": 55e9, "year": 2023},
    "2024-12-31": {"value": 60e9, "year": 2024},
}

FAKE_ITR = {
    "2024-03-31": {"value": 56e9, "meses": 3, "year": 2024},
    "2024-06-30": {"value": 58e9, "meses": 6, "year": 2024},
}


# -- intangibles_at() tests --------------------------------------------------

class TestIntangiblesAt:
    def test_basic_computation(self, monkeypatch):
        """intangibles_at should return the most recent snapshot <= date."""
        monkeypatch.setattr(intangibles_engine, "_get_dfp_intangibles", lambda c: FAKE_DFP)
        monkeypatch.setattr(intangibles_engine, "_get_itr_intangibles", lambda c: FAKE_ITR)

        # At 2024-07-15 -> most recent snapshot is ITR 2024-06-30 (58e9)
        result = intangibles_engine.intangibles_at("PETR4", "2024-07-15")
        assert result == 58e9

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """Before any ITR snapshot, fall back to most recent DFP."""
        monkeypatch.setattr(intangibles_engine, "_get_dfp_intangibles", lambda c: FAKE_DFP)
        monkeypatch.setattr(intangibles_engine, "_get_itr_intangibles", lambda c: FAKE_ITR)

        # At 2024-01-15 -> most recent snapshot is DFP 2023-12-31 (55e9)
        result = intangibles_engine.intangibles_at("PETR4", "2024-01-15")
        assert result == 55e9

    def test_missing_company(self, monkeypatch):
        """Missing company (no data) -> None."""
        monkeypatch.setattr(intangibles_engine, "_get_dfp_intangibles", lambda c: {})
        monkeypatch.setattr(intangibles_engine, "_get_itr_intangibles", lambda c: {})

        assert intangibles_engine.intangibles_at("UNKNOWN", "2024-06-30") is None

    def test_no_snapshot_before_date(self, monkeypatch):
        """All snapshots after the requested date -> None."""
        monkeypatch.setattr(intangibles_engine, "_get_dfp_intangibles", lambda c: FAKE_DFP)
        monkeypatch.setattr(intangibles_engine, "_get_itr_intangibles", lambda c: FAKE_ITR)

        # 2020 is before any snapshot
        assert intangibles_engine.intangibles_at("PETR4", "2020-01-01") is None


# -- intangibles_periods() tests ---------------------------------------------

class TestIntangiblesPeriods:
    def test_periods(self, monkeypatch):
        """intangibles_periods returns list of {date, intangibles} sorted oldest-first."""
        monkeypatch.setattr(intangibles_engine, "_get_dfp_intangibles", lambda c: FAKE_DFP)
        monkeypatch.setattr(intangibles_engine, "_get_itr_intangibles", lambda c: FAKE_ITR)

        result = intangibles_engine.intangibles_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) == 4  # 2 DFP + 2 ITR (distinct dates)

        # Sorted oldest-first
        assert result[0]["date"] == "2023-12-31"
        assert result[-1]["date"] == "2024-12-31"

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "intangibles" in entry
            assert isinstance(entry["intangibles"], float)

    def test_periods_empty_when_no_data(self, monkeypatch):
        monkeypatch.setattr(intangibles_engine, "_get_dfp_intangibles", lambda c: {})
        monkeypatch.setattr(intangibles_engine, "_get_itr_intangibles", lambda c: {})

        assert intangibles_engine.intangibles_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestIntangiblesRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "intangibles" in ENGINES
        spec = ENGINES["intangibles"]
        assert spec.name == "intangibles"
        assert spec.category == "bpa"
        assert spec.quantity == "intangibles"
        assert spec.at_fn is intangibles_engine.intangibles_at
        assert spec.periods_fn is intangibles_engine.intangibles_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query BPA codigo 1.02.04 (Intangível)."""
        assert intangibles_engine.INTANGIVEL_CODE == "1.02.04"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "1.02.04" in ENGINES["intangibles"].source
