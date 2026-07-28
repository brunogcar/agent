"""Tests for skills/cvm/calculations/engines/ppe.py.

Snapshot engine (BPA codigo 1.02.03 -- Imobilizado / Property, Plant &
Equipment, point-in-time balance, no TTM derivation). Mocks the internal
_get_dfp_ppe + _get_itr_ppe functions via monkeypatch -- no database
needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import ppe as ppe_engine


# -- Mock data ---------------------------------------------------------------

FAKE_DFP = {
    "2023-12-31": {"value": 390e9, "year": 2023},
    "2024-12-31": {"value": 400e9, "year": 2024},
}

FAKE_ITR = {
    "2024-03-31": {"value": 392e9, "meses": 3, "year": 2024},
    "2024-06-30": {"value": 395e9, "meses": 6, "year": 2024},
}


# -- ppe_at() tests ----------------------------------------------------------

class TestPpeAt:
    def test_basic_computation(self, monkeypatch):
        """ppe_at should return the most recent snapshot <= date."""
        monkeypatch.setattr(ppe_engine, "_get_dfp_ppe", lambda c: FAKE_DFP)
        monkeypatch.setattr(ppe_engine, "_get_itr_ppe", lambda c: FAKE_ITR)

        # At 2024-07-15 -> most recent snapshot is ITR 2024-06-30 (395e9)
        result = ppe_engine.ppe_at("PETR4", "2024-07-15")
        assert result == 395e9

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """Before any ITR snapshot, fall back to most recent DFP."""
        monkeypatch.setattr(ppe_engine, "_get_dfp_ppe", lambda c: FAKE_DFP)
        monkeypatch.setattr(ppe_engine, "_get_itr_ppe", lambda c: FAKE_ITR)

        # At 2024-01-15 -> most recent snapshot is DFP 2023-12-31 (390e9)
        result = ppe_engine.ppe_at("PETR4", "2024-01-15")
        assert result == 390e9

    def test_missing_company(self, monkeypatch):
        """Missing company (no data) -> None."""
        monkeypatch.setattr(ppe_engine, "_get_dfp_ppe", lambda c: {})
        monkeypatch.setattr(ppe_engine, "_get_itr_ppe", lambda c: {})

        assert ppe_engine.ppe_at("UNKNOWN", "2024-06-30") is None

    def test_no_snapshot_before_date(self, monkeypatch):
        """All snapshots after the requested date -> None."""
        monkeypatch.setattr(ppe_engine, "_get_dfp_ppe", lambda c: FAKE_DFP)
        monkeypatch.setattr(ppe_engine, "_get_itr_ppe", lambda c: FAKE_ITR)

        # 2020 is before any snapshot
        assert ppe_engine.ppe_at("PETR4", "2020-01-01") is None


# -- ppe_periods() tests -----------------------------------------------------

class TestPpePeriods:
    def test_periods(self, monkeypatch):
        """ppe_periods returns list of {date, ppe} sorted oldest-first."""
        monkeypatch.setattr(ppe_engine, "_get_dfp_ppe", lambda c: FAKE_DFP)
        monkeypatch.setattr(ppe_engine, "_get_itr_ppe", lambda c: FAKE_ITR)

        result = ppe_engine.ppe_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) == 4  # 2 DFP + 2 ITR (distinct dates)

        # Sorted oldest-first
        assert result[0]["date"] == "2023-12-31"
        assert result[-1]["date"] == "2024-12-31"

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "ppe" in entry
            assert isinstance(entry["ppe"], float)

    def test_periods_empty_when_no_data(self, monkeypatch):
        monkeypatch.setattr(ppe_engine, "_get_dfp_ppe", lambda c: {})
        monkeypatch.setattr(ppe_engine, "_get_itr_ppe", lambda c: {})

        assert ppe_engine.ppe_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestPpeRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "ppe" in ENGINES
        spec = ENGINES["ppe"]
        assert spec.name == "ppe"
        assert spec.category == "bpa"
        assert spec.quantity == "ppe"
        assert spec.at_fn is ppe_engine.ppe_at
        assert spec.periods_fn is ppe_engine.ppe_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query BPA codigo 1.02.03 (Imobilizado)."""
        assert ppe_engine.IMOBILIZADO_CODE == "1.02.03"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "1.02.03" in ENGINES["ppe"].source
