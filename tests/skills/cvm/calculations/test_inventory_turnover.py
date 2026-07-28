"""Tests for Inventory Turnover = abs(COGS) / Inventory.

Fundamental ratio (per_share=None). Guards: inventory > 0; COGS not None.
COGS is typically NEGATIVE on the DRE -- this metric uses abs(COGS).
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import inventory_turnover as ito_metric


class TestInventoryTurnover:
    def test_basic_computation(self, monkeypatch):
        """abs(COGS) / inventory -- COGS negative on DRE."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.cogs_at",
                            lambda c, d: -150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.inventory_at",
                            lambda c, d: 30e9)
        # |COGS| / inventory = 150 / 30 = 5.0
        result = ito_metric.inventory_turnover_at("PETR4", "2024-06-30")
        assert result == pytest.approx(5.0, rel=1e-3)

    def test_positive_cogs_also_works(self, monkeypatch):
        """If a filer reports COGS as positive (rare), abs() handles it."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.cogs_at",
                            lambda c, d: 150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.inventory_at",
                            lambda c, d: 30e9)
        result = ito_metric.inventory_turnover_at("PETR4", "2024-06-30")
        assert result == pytest.approx(5.0, rel=1e-3)

    def test_missing_cogs_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.cogs_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.inventory_at",
                            lambda c, d: 30e9)
        assert ito_metric.inventory_turnover_at("PETR4", "2024-06-30") is None

    def test_missing_inventory_none(self, monkeypatch):
        """Missing inventory (e.g., service company) -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.cogs_at",
                            lambda c, d: -150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.inventory_at",
                            lambda c, d: None)
        assert ito_metric.inventory_turnover_at("PETR4", "2024-06-30") is None

    def test_zero_inventory_none(self, monkeypatch):
        """Zero inventory -> None (denominator)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.cogs_at",
                            lambda c, d: -150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.inventory_at",
                            lambda c, d: 0)
        assert ito_metric.inventory_turnover_at("PETR4", "2024-06-30") is None

    def test_negative_inventory_none(self, monkeypatch):
        """Negative inventory -> None (denominator must be > 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.cogs_at",
                            lambda c, d: -150e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.inventory_at",
                            lambda c, d: -5e9)
        assert ito_metric.inventory_turnover_at("PETR4", "2024-06-30") is None

    def test_zero_cogs_zero_turnover(self, monkeypatch):
        """Zero COGS -> 0.0 turnover (valid; means no sales)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.cogs_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.inventory_turnover.inventory_at",
                            lambda c, d: 30e9)
        assert ito_metric.inventory_turnover_at("PETR4", "2024-06-30") == 0.0

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["inventory_turnover"].ratio_key == "inventory_turnover"
        assert METRICS["inventory_turnover"].per_share_key is None
        assert resolve_metric("giro_estoque").name == "inventory_turnover"
        assert resolve_metric("ito").name == "inventory_turnover"
        assert resolve_metric("inventory_turn").name == "inventory_turnover"
