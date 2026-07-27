"""Tests for Tier 4 metrics: Net Margin, EBITDA Margin, Debt/Equity,
Net Debt/EBITDA, Asset Turnover.

All 5 are fundamental ratios (per_share=None) composing existing engines.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Net Margin = earnings / revenue
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import net_margin as nm_metric


class TestNetMargin:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.net_margin.ttm_earnings_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_margin.revenue_at", lambda c, d: 280e9)
        assert nm_metric.net_margin_at("PETR4", "2024-06-30") == pytest.approx(0.25, rel=1e-3)

    def test_negative_earnings_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.net_margin.ttm_earnings_at", lambda c, d: -10e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_margin.revenue_at", lambda c, d: 280e9)
        assert nm_metric.net_margin_at("PETR4", "2024-06-30") is None

    def test_missing_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.net_margin.ttm_earnings_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_margin.revenue_at", lambda c, d: None)
        assert nm_metric.net_margin_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.historical._registry import METRICS, resolve_metric
        assert METRICS["net_margin"].ratio_key == "net_margin"
        assert METRICS["net_margin"].per_share_key is None
        assert resolve_metric("margem_liquida").name == "net_margin"
        assert resolve_metric("ml").name == "net_margin"


# ════════════════════════════════════════════════════════════════════════════
# EBITDA Margin = (EBIT + D&A) / revenue
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import ebitda_margin as em_metric


class TestEbitdaMargin:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.da_at", lambda c, d: 15e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.revenue_at", lambda c, d: 280e9)
        # EBITDA = 85e9, margin = 85e9/280e9 = 0.303...
        assert em_metric.ebitda_margin_at("PETR4", "2024-06-30") == pytest.approx(85e9 / 280e9, rel=1e-3)

    def test_negative_ebitda_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.ebit_at", lambda c, d: -20e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.da_at", lambda c, d: 15e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.revenue_at", lambda c, d: 280e9)
        assert em_metric.ebitda_margin_at("PETR4", "2024-06-30") is None

    def test_missing_da_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.da_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.ebitda_margin.revenue_at", lambda c, d: 280e9)
        assert em_metric.ebitda_margin_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.historical._registry import METRICS, resolve_metric
        assert METRICS["ebitda_margin"].ratio_key == "ebitda_margin"
        assert resolve_metric("margem_ebitda").name == "ebitda_margin"
        assert resolve_metric("em").name == "ebitda_margin"


# ════════════════════════════════════════════════════════════════════════════
# Debt/Equity = debt / PL
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import debt_equity as de_metric


class TestDebtEquity:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.pl_at", lambda c, d: 350e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") == pytest.approx(100e9 / 350e9, rel=1e-3)

    def test_zero_debt(self, monkeypatch):
        """Zero debt is valid (D/E = 0)."""
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.debt_at", lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.pl_at", lambda c, d: 350e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") == 0.0

    def test_negative_pl_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.pl_at", lambda c, d: -50e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") is None

    def test_missing_debt_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.debt_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.debt_equity.pl_at", lambda c, d: 350e9)
        assert de_metric.debt_equity_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.historical._registry import METRICS, resolve_metric
        assert METRICS["debt_equity"].ratio_key == "debt_equity"
        assert resolve_metric("divida_pl").name == "debt_equity"
        assert resolve_metric("divida_patrimonio").name == "debt_equity"


# ════════════════════════════════════════════════════════════════════════════
# Net Debt / EBITDA = (debt - cash) / (EBIT + D&A)
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import net_debt_ebitda as nde_metric


class TestNetDebtEbitda:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        # Net debt = 70e9, EBITDA = 85e9, ratio = 70e9/85e9 = 0.823...
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") == pytest.approx(70e9 / 85e9, rel=1e-3)

    def test_net_cash_negative_ratio(self, monkeypatch):
        """If cash > debt, net debt is negative (net cash position). Ratio is negative."""
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.debt_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.cash_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        # Net debt = -70e9, EBITDA = 85e9, ratio = -0.823...
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") == pytest.approx(-70e9 / 85e9, rel=1e-3)

    def test_negative_ebitda_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.cash_at", lambda c, d: 30e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.ebit_at", lambda c, d: -20e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") is None

    def test_missing_cash_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.debt_at", lambda c, d: 100e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.cash_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.ebit_at", lambda c, d: 70e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.net_debt_ebitda.da_at", lambda c, d: 15e9)
        assert nde_metric.net_debt_ebitda_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.historical._registry import METRICS, resolve_metric
        assert METRICS["net_debt_ebitda"].ratio_key == "net_debt_ebitda"
        assert resolve_metric("dl_ebitda").name == "net_debt_ebitda"
        assert resolve_metric("divida_liquida_ebitda").name == "net_debt_ebitda"


# ════════════════════════════════════════════════════════════════════════════
# Asset Turnover = revenue / assets
# ════════════════════════════════════════════════════════════════════════════

from skills.cvm.historical.metrics import asset_turnover as at_metric


class TestAssetTurnover:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.asset_turnover.revenue_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.asset_turnover.assets_at", lambda c, d: 800e9)
        assert at_metric.asset_turnover_at("PETR4", "2024-06-30") == pytest.approx(280e9 / 800e9, rel=1e-3)

    def test_missing_revenue_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.asset_turnover.revenue_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.historical.metrics.asset_turnover.assets_at", lambda c, d: 800e9)
        assert at_metric.asset_turnover_at("PETR4", "2024-06-30") is None

    def test_missing_assets_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.historical.metrics.asset_turnover.revenue_at", lambda c, d: 280e9)
        monkeypatch.setattr("skills.cvm.historical.metrics.asset_turnover.assets_at", lambda c, d: None)
        assert at_metric.asset_turnover_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        from skills.cvm.historical._registry import METRICS, resolve_metric
        assert METRICS["asset_turnover"].ratio_key == "asset_turnover"
        assert resolve_metric("giro_ativos").name == "asset_turnover"
        assert resolve_metric("at").name == "asset_turnover"
