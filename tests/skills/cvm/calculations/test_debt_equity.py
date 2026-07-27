"""Tests for Debt/Equity = debt / PL.

Fundamental ratio (per_share=None) composing existing engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Debt/Equity = debt / PL
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import debt_equity as de_metric


class TestDebtEquity:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.pl_at", lambda c, d: 350e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") == pytest.approx(100e9 / 350e9, rel=1e-3)

    def test_zero_debt(self, monkeypatch):
        """Zero debt is valid (D/E = 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.debt_at", lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.pl_at", lambda c, d: 350e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") == 0.0

    def test_negative_pl_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.pl_at", lambda c, d: -50e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") is None

    def test_missing_debt_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.debt_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.debt_equity.pl_at", lambda c, d: 350e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["debt_equity"].ratio_key == "debt_equity"
        assert resolve_metric("divida_pl").name == "debt_equity"
        assert resolve_metric("divida_patrimonio").name == "debt_equity"
