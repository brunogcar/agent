"""Tests for Net Debt / EBITDA = (debt - cash) / (EBIT + D&A).

Fundamental ratio (per_share=None) composing existing engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Net Debt / EBITDA = (debt - cash) / (EBIT + D&A)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.calculations.metrics import net_debt_ebitda as nde_metric


class TestNetDebtEbitda:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        # Net debt = 70e9, EBITDA = 85e9, ratio = 70e9/85e9 = 0.823...
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") == pytest.approx(70e9 / 85e9, rel=1e-3)

    def test_net_cash_negative_ratio(self, monkeypatch):
        """If cash > debt, net debt is negative (net cash position). Ratio is negative."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.debt_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.cash_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        # Net debt = -70e9, EBITDA = 85e9, ratio = -0.823...
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") == pytest.approx(-70e9 / 85e9, rel=1e-3)

    def test_negative_ebitda_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.ebit_at", lambda c, d: -20e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") is None

    def test_missing_cash_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.cash_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["net_debt_ebitda"].ratio_key == "net_debt_ebitda"
        assert resolve_metric("dl_ebitda").name == "net_debt_ebitda"
        assert resolve_metric("divida_liquida_ebitda").name == "net_debt_ebitda"
