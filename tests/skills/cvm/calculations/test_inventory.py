"""Tests for skills/cvm/calculations/engines/inventory.py.

Snapshot engine (BPA codigo 1.01.04 -- Estoques, point-in-time balance,
no TTM derivation). Mocks the internal _get_dfp_inventory +
_get_itr_inventory functions via monkeypatch -- no database needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.engines import inventory as inventory_engine


# -- Mock data ---------------------------------------------------------------

FAKE_DFP = {
    "2023-12-31": {"value": 22e9, "year": 2023},
    "2024-12-31": {"value": 25e9, "year": 2024},
}

FAKE_ITR = {
    "2024-03-31": {"value": 23e9, "meses": 3, "year": 2024},
    "2024-06-30": {"value": 24e9, "meses": 6, "year": 2024},
}


# -- inventory_at() tests ----------------------------------------------------

class TestInventoryAt:
    def test_basic_computation(self, monkeypatch):
        """inventory_at should return the most recent snapshot <= date."""
        monkeypatch.setattr(inventory_engine, "_get_dfp_inventory", lambda c: FAKE_DFP)
        monkeypatch.setattr(inventory_engine, "_get_itr_inventory", lambda c: FAKE_ITR)

        # At 2024-07-15 -> most recent snapshot is ITR 2024-06-30 (24e9)
        result = inventory_engine.inventory_at("PETR4", "2024-07-15")
        assert result == 24e9

    def test_returns_dfp_when_no_itr_before_date(self, monkeypatch):
        """Before any ITR snapshot, fall back to most recent DFP."""
        monkeypatch.setattr(inventory_engine, "_get_dfp_inventory", lambda c: FAKE_DFP)
        monkeypatch.setattr(inventory_engine, "_get_itr_inventory", lambda c: FAKE_ITR)

        # At 2024-01-15 -> most recent snapshot is DFP 2023-12-31 (22e9)
        result = inventory_engine.inventory_at("PETR4", "2024-01-15")
        assert result == 22e9

    def test_missing_company(self, monkeypatch):
        """Missing company (no data) -> None."""
        monkeypatch.setattr(inventory_engine, "_get_dfp_inventory", lambda c: {})
        monkeypatch.setattr(inventory_engine, "_get_itr_inventory", lambda c: {})

        assert inventory_engine.inventory_at("UNKNOWN", "2024-06-30") is None

    def test_no_snapshot_before_date(self, monkeypatch):
        """All snapshots after the requested date -> None."""
        monkeypatch.setattr(inventory_engine, "_get_dfp_inventory", lambda c: FAKE_DFP)
        monkeypatch.setattr(inventory_engine, "_get_itr_inventory", lambda c: FAKE_ITR)

        # 2020 is before any snapshot
        assert inventory_engine.inventory_at("PETR4", "2020-01-01") is None


# -- inventory_periods() tests -----------------------------------------------

class TestInventoryPeriods:
    def test_periods(self, monkeypatch):
        """inventory_periods returns list of {date, inventory} sorted oldest-first."""
        monkeypatch.setattr(inventory_engine, "_get_dfp_inventory", lambda c: FAKE_DFP)
        monkeypatch.setattr(inventory_engine, "_get_itr_inventory", lambda c: FAKE_ITR)

        result = inventory_engine.inventory_periods("PETR4")
        assert isinstance(result, list)
        assert len(result) == 4  # 2 DFP + 2 ITR (distinct dates)

        # Sorted oldest-first
        assert result[0]["date"] == "2023-12-31"
        assert result[-1]["date"] == "2024-12-31"

        # Each entry has the correct key
        for entry in result:
            assert "date" in entry
            assert "inventory" in entry
            assert isinstance(entry["inventory"], float)

    def test_periods_empty_when_no_data(self, monkeypatch):
        monkeypatch.setattr(inventory_engine, "_get_dfp_inventory", lambda c: {})
        monkeypatch.setattr(inventory_engine, "_get_itr_inventory", lambda c: {})

        assert inventory_engine.inventory_periods("UNKNOWN") == []


# -- Registry tests ----------------------------------------------------------

class TestInventoryRegistry:
    def test_registry(self):
        """Engine should be registered with correct name, category, quantity."""
        from skills.cvm.calculations._registry import ENGINES
        assert "inventory" in ENGINES
        spec = ENGINES["inventory"]
        assert spec.name == "inventory"
        assert spec.category == "bpa"
        assert spec.quantity == "inventory"
        assert spec.at_fn is inventory_engine.inventory_at
        assert spec.periods_fn is inventory_engine.inventory_periods

    def test_uses_correct_cvm_code(self):
        """Engine should query BPA codigo 1.01.04 (Estoques)."""
        assert inventory_engine.ESTOQUES_CODE == "1.01.04"

    def test_source_mentions_codigo(self):
        """Engine source string should mention the CVM code for documentation."""
        from skills.cvm.calculations._registry import ENGINES
        assert "1.01.04" in ENGINES["inventory"].source
