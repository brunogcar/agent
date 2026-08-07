"""Tests for skills/cvm/calculations/metrics/altman_z.py.

[v2.0]

Altman Z-Score (original 1968 manufacturing model):
  Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5

  X1 = Working Capital / Total Assets
  X2 = Retained Earnings / Total Assets  [PROXY: PL / Total Assets]
  X3 = EBIT / Total Assets
  X4 = Market Cap / Total Liabilities
  X5 = Sales / Total Assets

Mocks the 8 underlying engines — no database needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import altman_z as altman_metric


# ── Mock helpers ─────────────────────────────────────────────────────────────

def _mock_altman_inputs(
    monkeypatch,
    *,
    current_assets: float | None = 150e9,
    current_liabilities: float | None = 100e9,
    total_assets: float | None = 500e9,
    pl: float | None = 200e9,
    ebit: float | None = 60e9,
    revenue: float | None = 300e9,
    price: float | None = 38.0,
    shares: float | None = 13e9,
):
    """Mock the 8 engines Altman Z-Score depends on.

    Default values produce a "safe" company:
      X1 = (150 − 100) / 500       = 0.10
      X2 = 200 / 500               = 0.40
      X3 = 60 / 500                = 0.12
      X4 = (38 × 13e9) / (500-200) = 494e9 / 300e9 = 1.6467
      X5 = 300 / 500               = 0.60
      Z = 1.2×0.10 + 1.4×0.40 + 3.3×0.12 + 0.6×1.6467 + 1.0×0.60
        = 0.12 + 0.56 + 0.396 + 0.988 + 0.60
        = 2.664  (grey zone)
    """
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.current_assets_at",
        lambda c, d: current_assets,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.current_liabilities_at",
        lambda c, d: current_liabilities,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.total_assets_at",
        lambda c, d: total_assets,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.pl_at",
        lambda c, d: pl,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.ebit_at",
        lambda c, d: ebit,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.revenue_at",
        lambda c, d: revenue,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.price_at",
        lambda c, d: price,
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.altman_z.shares_at",
        lambda c, d: shares,
    )


def _compute_z(
    current_assets: float,
    current_liabilities: float,
    total_assets: float,
    pl: float,
    ebit: float,
    revenue: float,
    price: float,
    shares: float,
) -> float:
    """Reference implementation -- mirrors altman_z_at() math for assertions."""
    total_liabilities = total_assets - pl
    market_cap = price * shares
    x1 = (current_assets - current_liabilities) / total_assets
    x2 = pl / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_liabilities
    x5 = revenue / total_assets
    return 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5


# ── Tests ────────────────────────────────────────────────────────────────────

class TestAltmanZAt:
    def test_basic_computation(self, monkeypatch):
        """Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5.

        Default mocks produce Z ≈ 2.664 (grey zone).
        """
        _mock_altman_inputs(monkeypatch)
        result = altman_metric.altman_z_at("PETR4", "2024-06-30")
        assert result is not None

        expected = _compute_z(
            150e9, 100e9, 500e9, 200e9, 60e9, 300e9, 38.0, 13e9
        )
        assert result == pytest.approx(expected, rel=1e-6)
        # Sanity: grey zone (1.81 < Z < 2.99)
        assert 1.81 < result < 2.99

    def test_safe_zone(self, monkeypatch):
        """A highly profitable, low-leverage company should be in the safe
        zone (Z > 2.99)."""
        _mock_altman_inputs(
            monkeypatch,
            current_assets=300e9,   # big working capital
            current_liabilities=80e9,
            total_assets=500e9,
            pl=350e9,               # big equity → small liabilities
            ebit=120e9,             # high EBIT
            revenue=400e9,
            price=50.0,
            shares=20e9,
        )
        result = altman_metric.altman_z_at("PETR4", "2024-06-30")
        assert result is not None
        assert result > 2.99  # safe zone

    def test_distress_zone(self, monkeypatch):
        """A loss-making, high-leverage company should be in the distress
        zone (Z < 1.81)."""
        _mock_altman_inputs(
            monkeypatch,
            current_assets=80e9,    # low working capital
            current_liabilities=200e9,  # high current liabilities
            total_assets=500e9,
            pl=50e9,                # tiny equity → huge liabilities
            ebit=-20e9,             # operating loss
            revenue=200e9,
            price=5.0,              # low market cap
            shares=10e9,
        )
        result = altman_metric.altman_z_at("PETR4", "2024-06-30")
        assert result is not None
        assert result < 1.81  # distress zone

    def test_negative_z_for_severe_distress(self, monkeypatch):
        """A company with operating losses, negative working capital, and
        tiny market cap can produce a negative Z.

        Setup:
          X1 = (30 − 250) / 500 = −0.44   (negative working capital)
          X2 = 50 / 500          = 0.10   (small equity relative to assets)
          X3 = −200 / 500        = −0.40  (large operating loss)
          X4 = (1 × 1e9) / 450   = 0.0022 (tiny market cap vs huge liabilities)
          X5 = 100 / 500         = 0.20   (low asset turnover)
          Z = 1.2×(−0.44) + 1.4×0.10 + 3.3×(−0.40) + 0.6×0.0022 + 1.0×0.20
            = −0.528 + 0.14 − 1.32 + 0.0013 + 0.20
            = −1.507  (severe distress)
        """
        _mock_altman_inputs(
            monkeypatch,
            current_assets=30e9,
            current_liabilities=250e9,  # working capital = -220B (negative!)
            total_assets=500e9,
            pl=50e9,                    # tiny equity → huge liabilities = 450B
            ebit=-200e9,                # large operating loss
            revenue=100e9,
            price=1.0,                  # tiny market cap = 1B
            shares=1e9,
        )
        result = altman_metric.altman_z_at("PETR4", "2024-06-30")
        assert result is not None
        assert result < 0  # severe distress

    def test_none_total_assets_returns_none(self, monkeypatch):
        """Missing total_assets → X1, X2, X3, X5 undefined → None."""
        _mock_altman_inputs(monkeypatch, total_assets=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_zero_total_assets_returns_none(self, monkeypatch):
        """Zero total_assets → division by zero → None."""
        _mock_altman_inputs(monkeypatch, total_assets=0.0)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_none_pl_returns_none(self, monkeypatch):
        """Missing PL → can't compute total_liabilities → None."""
        _mock_altman_inputs(monkeypatch, pl=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_zero_total_liabilities_returns_none(self, monkeypatch):
        """When total_assets == PL → total_liabilities = 0 → X4 undefined
        (÷0) → None."""
        _mock_altman_inputs(monkeypatch, total_assets=500e9, pl=500e9)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_none_current_assets_returns_none(self, monkeypatch):
        _mock_altman_inputs(monkeypatch, current_assets=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_none_current_liabilities_returns_none(self, monkeypatch):
        _mock_altman_inputs(monkeypatch, current_liabilities=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_none_ebit_returns_none(self, monkeypatch):
        _mock_altman_inputs(monkeypatch, ebit=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_none_revenue_returns_none(self, monkeypatch):
        _mock_altman_inputs(monkeypatch, revenue=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_none_price_returns_none(self, monkeypatch):
        _mock_altman_inputs(monkeypatch, price=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_none_shares_returns_none(self, monkeypatch):
        _mock_altman_inputs(monkeypatch, shares=None)
        assert altman_metric.altman_z_at("PETR4", "2024-06-30") is None

    def test_negative_liabilities_still_computes(self, monkeypatch):
        """When PL > Total Assets, total_liabilities goes negative.
        X4 = market_cap / negative_liabilities → negative X4.
        The metric should still compute (Z will be lower)."""
        _mock_altman_inputs(
            monkeypatch,
            total_assets=500e9,
            pl=600e9,  # PL > Total Assets → liabilities = -100B
        )
        result = altman_metric.altman_z_at("PETR4", "2024-06-30")
        assert result is not None  # did not blow up
        # X4 will be negative → Z lower than default
        expected = _compute_z(
            150e9, 100e9, 500e9, 600e9, 60e9, 300e9, 38.0, 13e9
        )
        assert result == pytest.approx(expected, rel=1e-6)


class TestAltmanZZone:
    """Tests for the zone classification (used by altman_z_history)."""

    def test_zone_safe(self):
        from skills.cvm.calculations.metrics.altman_z import _zone
        assert _zone(3.5) == "safe"
        assert _zone(2.99 + 0.001) == "safe"

    def test_zone_grey(self):
        from skills.cvm.calculations.metrics.altman_z import _zone
        assert _zone(2.5) == "grey"
        assert _zone(2.99) == "grey"  # boundary: not > 2.99
        assert _zone(1.81) == "grey"  # boundary: not < 1.81

    def test_zone_distress(self):
        from skills.cvm.calculations.metrics.altman_z import _zone
        assert _zone(1.5) == "distress"
        assert _zone(1.81 - 0.001) == "distress"
        assert _zone(-2.0) == "distress"  # severe distress still "distress"

    def test_zone_none(self):
        from skills.cvm.calculations.metrics.altman_z import _zone
        assert _zone(None) is None


class TestAltmanZHistory:
    """Tests for the time series — verifies X1-X5 + Z + zone are returned."""

    def _mock_periods(self, monkeypatch):
        """Mock the 3 TTM/snapshot periods functions used by history."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.total_assets_periods",
            lambda c: [
                {"date": "2023-12-31", "total_assets": 480e9},
                {"date": "2024-03-31", "total_assets": 490e9},
                {"date": "2024-06-30", "total_assets": 500e9},
            ],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.revenue_periods",
            lambda c: [
                {"date": "2023-12-31", "ttm_rev": 280e9},
                {"date": "2024-03-31", "ttm_rev": 290e9},
                {"date": "2024-06-30", "ttm_rev": 300e9},
            ],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.ebit_periods",
            lambda c: [
                {"date": "2023-12-31", "ttm_ebit": 55e9},
                {"date": "2024-03-31", "ttm_ebit": 58e9},
                {"date": "2024-06-30", "ttm_ebit": 60e9},
            ],
        )
        # Snapshot engines — return constants for simplicity
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.pl_at",
            lambda c, d: 200e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.current_assets_at",
            lambda c, d: 150e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.current_liabilities_at",
            lambda c, d: 100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.price_at",
            lambda c, d: 38.0,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.shares_at",
            lambda c, d: 13e9,
        )

    def test_basic_shape(self, monkeypatch):
        """Each history entry has all 7 expected keys."""
        self._mock_periods(monkeypatch)
        result = altman_metric.altman_z_history(
            "PETR4", "2023-01-01", "2024-12-31"
        )
        assert len(result) >= 3
        for entry in result:
            assert "date" in entry
            assert "altman_z" in entry
            assert "x1" in entry
            assert "x2" in entry
            assert "x3" in entry
            assert "x4" in entry
            assert "x5" in entry
            assert "zone" in entry

    def test_zone_matches_z(self, monkeypatch):
        """zone must match the Z value via the standard thresholds."""
        self._mock_periods(monkeypatch)
        result = altman_metric.altman_z_history(
            "PETR4", "2023-01-01", "2024-12-31"
        )
        for entry in result:
            z = entry["altman_z"]
            zone = entry["zone"]
            if z is None:
                assert zone is None
            elif z > 2.99:
                assert zone == "safe"
            elif z < 1.81:
                assert zone == "distress"
            else:
                assert zone == "grey"

    def test_empty_periods_returns_empty(self, monkeypatch):
        """When all 3 periods functions return [], history should be empty."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.total_assets_periods",
            lambda c: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.revenue_periods",
            lambda c: [],
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.altman_z.ebit_periods",
            lambda c: [],
        )
        assert altman_metric.altman_z_history(
            "PETR4", "2024-01-01", "2024-12-31"
        ) == []

    def test_sorted_oldest_first(self, monkeypatch):
        """Entries must be sorted oldest-first."""
        self._mock_periods(monkeypatch)
        result = altman_metric.altman_z_history(
            "PETR4", "2023-01-01", "2024-12-31"
        )
        dates = [entry["date"] for entry in result]
        assert dates == sorted(dates)


class TestAltmanZRegistry:
    def test_altman_z_registered(self):
        """Verify altman_z is registered in the metric registry."""
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert "altman_z" in METRICS
        spec = METRICS["altman_z"]
        assert spec.ratio_key == "altman_z"
        assert spec.ratio_label == "Altman Z-Score"
        assert spec.per_share_key is None
        assert spec.per_share_fn is None
        assert spec.category == "leverage"
        assert spec.allow_negative is True  # Z can be negative
        assert resolve_metric("altman_z").name == "altman_z"

    def test_altman_z_engines(self):
        """Verify altman_z lists all 8 composed engines."""
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["altman_z"]
        assert "current_assets" in spec.engines
        assert "current_liabilities" in spec.engines
        assert "total_assets" in spec.engines
        assert "pl" in spec.engines
        assert "ebit" in spec.engines
        assert "revenue" in spec.engines
        assert "price" in spec.engines
        assert "shares" in spec.engines

    def test_altman_z_tooltip(self):
        """Verify the tooltip mentions the formula + zone thresholds."""
        from skills.cvm.calculations._registry import METRICS
        spec = METRICS["altman_z"]
        assert spec.tooltip is not None
        assert "1.2" in spec.tooltip
        assert "1.4" in spec.tooltip
        assert "3.3" in spec.tooltip
        assert "0.6" in spec.tooltip
        assert "1.0" in spec.tooltip
        # Thresholds mentioned in PT-BR
        assert "2.99" in spec.tooltip
        assert "1.81" in spec.tooltip

    def test_altman_z_aliases(self):
        """Verify the aliases resolve correctly."""
        from skills.cvm.calculations._registry import resolve_metric
        assert resolve_metric("altman_zscore").name == "altman_z"
        assert resolve_metric("zscore").name == "altman_z"
        assert resolve_metric("altman").name == "altman_z"
