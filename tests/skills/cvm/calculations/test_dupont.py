"""Tests for skills/cvm/calculations/metrics/dupont.py.

[v2.0]

DuPont 3-step ROE decomposition:
  ROE = Net Margin × Asset Turnover × Equity Multiplier
      = (Earnings / Revenue) × (Revenue / Total Assets) × (Total Assets / PL)

Mocks the 4 underlying engines (earnings, revenue, total_assets, pl) —
no database needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import dupont as dupont_metric


# ── Mock helpers ─────────────────────────────────────────────────────────────

def _mock_dupont_inputs(
    monkeypatch,
    *,
    earnings: float | None = 40e9,      # BRL 40B TTM earnings
    revenue: float | None = 300e9,      # BRL 300B TTM revenue
    total_assets: float | None = 500e9, # BRL 500B total assets
    pl: float | None = 200e9,           # BRL 200B equity
):
    """Mock the 4 engines DuPont depends on.

    Default values produce:
      Net Margin         = 40e9 / 300e9 = 0.1333...
      Asset Turnover     = 300e9 / 500e9 = 0.6
      Equity Multiplier  = 500e9 / 200e9 = 2.5
      ROE = 0.1333 × 0.6 × 2.5 = 0.20  (20%)
    """
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dupont.ttm_earnings_at",
        lambda c, d: earnings,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dupont.revenue_at",
        lambda c, d: revenue,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dupont.total_assets_at",
        lambda c, d: total_assets,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.dupont.pl_at",
        lambda c, d: pl,
    )


# ── Tests ────────────────────────────────────────────────────────────────────

class TestDupontAt:
    def test_basic_computation(self, monkeypatch):
        """ROE = Net Margin × Asset Turnover × Equity Multiplier.

        Default mocks:
          Net Margin        = 40e9 / 300e9 = 0.13333...
          Asset Turnover    = 300e9 / 500e9 = 0.6
          Equity Multiplier = 500e9 / 200e9 = 2.5
          ROE = 0.13333 × 0.6 × 2.5 = 0.20
        Also verifies the telescoping identity: ROE = Earnings / PL = 40/200 = 0.20.
        """
        _mock_dupont_inputs(monkeypatch)
        result = dupont_metric.dupont_at("PETR4", "2024-06-30")
        assert result is not None

        net_margin = 40e9 / 300e9
        asset_turnover = 300e9 / 500e9
        equity_multiplier = 500e9 / 200e9
        expected = net_margin * asset_turnover * equity_multiplier
        assert result == pytest.approx(expected, rel=1e-6)

        # Telescoping check: ROE should equal Earnings / PL
        assert result == pytest.approx(40e9 / 200e9, rel=1e-6)

    def test_zero_revenue_returns_none(self, monkeypatch):
        """Zero revenue → Net Margin undefined (÷0) AND Asset Turnover
        undefined (÷0) → None."""
        _mock_dupont_inputs(monkeypatch, revenue=0.0)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_zero_total_assets_returns_none(self, monkeypatch):
        """Zero total assets → Asset Turnover undefined AND Equity Multiplier
        undefined → None."""
        _mock_dupont_inputs(monkeypatch, total_assets=0.0)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_zero_pl_returns_none(self, monkeypatch):
        """Zero equity → Equity Multiplier undefined (÷0) → None."""
        _mock_dupont_inputs(monkeypatch, pl=0.0)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity → Equity Multiplier meaningless → None."""
        _mock_dupont_inputs(monkeypatch, pl=-50e9)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_none_earnings_returns_none(self, monkeypatch):
        """Missing earnings → Net Margin undefined → None."""
        _mock_dupont_inputs(monkeypatch, earnings=None)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_none_revenue_returns_none(self, monkeypatch):
        """Missing revenue → Net Margin + Asset Turnover undefined → None."""
        _mock_dupont_inputs(monkeypatch, revenue=None)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_none_total_assets_returns_none(self, monkeypatch):
        """Missing total_assets → Asset Turnover + Equity Multiplier undefined
        → None."""
        _mock_dupont_inputs(monkeypatch, total_assets=None)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_none_pl_returns_none(self, monkeypatch):
        """Missing PL → Equity Multiplier undefined → None."""
        _mock_dupont_inputs(monkeypatch, pl=None)
        assert dupont_metric.dupont_at("PETR4", "2024-06-30") is None

    def test_negative_earnings_yields_negative_roe(self, monkeypatch):
        """Negative earnings → negative Net Margin → negative ROE (loss-making
        firm). The decomposition still computes; allow_negative is False at
        the registry level (summary will filter it out), but the function
        itself returns the negative value."""
        _mock_dupont_inputs(monkeypatch, earnings=-20e9)
        result = dupont_metric.dupont_at("PETR4", "2024-06-30")
        assert result is not None
        assert result < 0
        # ROE = (-20/300) × (300/500) × (500/200) = -20/200 = -0.10
        assert result == pytest.approx(-20e9 / 200e9, rel=1e-6)

    def test_high_leverage_company(self, monkeypatch):
        """Equity Multiplier = 5.0 (highly leveraged): 1T assets / 0.2T PL."""
        _mock_dupont_inputs(
            monkeypatch,
            earnings=10e9,
            revenue=100e9,
            total_assets=1000e9,
            pl=200e9,
        )
        # Net Margin = 0.10, Asset Turnover = 0.10, Equity Multiplier = 5.0
        # ROE = 0.10 × 0.10 × 5.0 = 0.05
        result = dupont_metric.dupont_at("PETR4", "2024-06-30")
        assert result == pytest.approx(0.05, rel=1e-6)


class TestDupontHistory:
    """Tests for the time series -- verifies the 4-component decomposition
    is returned alongside the headline ROE."""

    def _mock_periods(self, monkeypatch):
        """Mock the 4 *_periods functions with a small quarterly series."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.ttm_earnings_periods",
            lambda c: [
                {"date": "2023-12-31", "ttm": 35e9},
                {"date": "2024-03-31", "ttm": 38e9},
                {"date": "2024-06-30", "ttm": 40e9},
            ],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.revenue_periods",
            lambda c: [
                {"date": "2023-12-31", "ttm_rev": 280e9},
                {"date": "2024-03-31", "ttm_rev": 290e9},
                {"date": "2024-06-30", "ttm_rev": 300e9},
            ],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.total_assets_periods",
            lambda c: [
                {"date": "2023-12-31", "total_assets": 480e9},
                {"date": "2024-03-31", "total_assets": 490e9},
                {"date": "2024-06-30", "total_assets": 500e9},
            ],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.pl_periods",
            lambda c: [
                {"date": "2023-12-31", "pl": 190e9},
                {"date": "2024-03-31", "pl": 195e9},
                {"date": "2024-06-30", "pl": 200e9},
            ],
        )

    def test_basic_shape(self, monkeypatch):
        """Each history entry has the 4 expected keys."""
        self._mock_periods(monkeypatch)
        result = dupont_metric.dupont_history(
            "PETR4", "2023-01-01", "2024-12-31"
        )
        assert len(result) >= 3
        for entry in result:
            assert "date" in entry
            assert "dupont_roe" in entry
            assert "net_margin" in entry
            assert "asset_turnover" in entry
            assert "equity_multiplier" in entry

    def test_roe_decomposition_at_each_date(self, monkeypatch):
        """dupont_roe should equal net_margin × asset_turnover × equity_multiplier
        at every date in the series."""
        self._mock_periods(monkeypatch)
        result = dupont_metric.dupont_history(
            "PETR4", "2023-01-01", "2024-12-31"
        )
        for entry in result:
            if entry["dupont_roe"] is not None:
                expected = (
                    entry["net_margin"]
                    * entry["asset_turnover"]
                    * entry["equity_multiplier"]
                )
                assert entry["dupont_roe"] == pytest.approx(expected, rel=1e-6)

    def test_empty_periods_returns_empty(self, monkeypatch):
        """When all 4 *_periods functions return [], history should be empty."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.ttm_earnings_periods",
            lambda c: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.revenue_periods",
            lambda c: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.total_assets_periods",
            lambda c: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.dupont.pl_periods",
            lambda c: [],
        )
        assert dupont_metric.dupont_history(
            "PETR4", "2024-01-01", "2024-12-31"
        ) == []

    def test_sorted_oldest_first(self, monkeypatch):
        """Entries must be sorted oldest-first."""
        self._mock_periods(monkeypatch)
        result = dupont_metric.dupont_history(
            "PETR4", "2023-01-01", "2024-12-31"
        )
        dates = [entry["date"] for entry in result]
        assert dates == sorted(dates)


class TestDupontRegistry:
    def test_dupont_registered(self):
        """Verify dupont is registered in the metric registry."""
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert "dupont" in METRICS
        spec = METRICS["dupont"]
        assert spec.ratio_key == "dupont_roe"
        assert spec.ratio_label == "DuPont ROE"
        assert spec.per_share_key is None
        assert spec.per_share_fn is None
        assert spec.category == "profitability"
        assert spec.allow_negative is False
        assert resolve_metric("dupont").name == "dupont"

    def test_dupont_engines(self):
        """Verify dupont lists all 4 composed engines."""
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["dupont"]
        assert "earnings" in spec.engines
        assert "revenue" in spec.engines
        assert "total_assets" in spec.engines
        assert "pl" in spec.engines

    def test_dupont_tooltip(self):
        """Verify the tooltip mentions all 3 components."""
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["dupont"]
        assert spec.tooltip is not None
        assert "Margem Líquida" in spec.tooltip
        assert "Giro do Ativo" in spec.tooltip
        assert "Multiplicador" in spec.tooltip

    def test_dupont_aliases(self):
        """Verify the aliases resolve correctly."""
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("dupont_roe").name == "dupont"
        assert resolve_metric("dupont_3step").name == "dupont"
        assert resolve_metric("roe_dupont").name == "dupont"
