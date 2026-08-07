"""Tests for skills/cvm/calculations/metrics/graham_number.py.

Graham Number = sqrt(22.5 × LPA × VPA) = sqrt(22.5 × EPS × Book Value per Share).
Mocks the underlying engines (earnings + pl + shares) — no database needed.

[v1.18 hardening] This file was previously a mislabeled copy of test_p_fco.py
(it imported p_fco, not graham_number). Now properly tests graham_number_at.
"""
from __future__ import annotations

import pytest


# ── Mock fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_engines(monkeypatch):
    """Mock the 3 engines graham_number depends on."""
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.graham_number.ttm_earnings_at",
        lambda c, d: 100e9,  # R$ 100B TTM earnings
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.graham_number.pl_at",
        lambda c, d: 300e9,  # R$ 300B PL
    )
    monkeypatch.setattr(
        "skills.cvm.calculations.metrics.graham_number.shares_at",
        lambda c, d: 13e9,   # 13 billion shares
    )


# ── Tests ────────────────────────────────────────────────────────────────────

class TestGrahamNumber:
    def test_basic_computation(self, mock_engines):
        """Graham Number = sqrt(22.5 × LPA × VPA).

        LPA = 100e9 / 13e9 = 7.6923
        VPA = 300e9 / 13e9 = 23.0769
        Product = 22.5 × 7.6923 × 23.0769 = 3994.06
        sqrt(3994.06) = 63.20
        """
        from skills.cvm.calculations.metrics.graham_number import graham_number_at
        result = graham_number_at("PETR4", "2024-06-30")
        expected = (22.5 * (100e9 / 13e9) * (300e9 / 13e9)) ** 0.5
        assert result is not None
        assert result == pytest.approx(expected, rel=1e-4)

    def test_negative_earnings_returns_none(self, monkeypatch):
        """Negative earnings → LPA < 0 → sqrt of negative product → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.ttm_earnings_at",
            lambda c, d: -10e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.pl_at",
            lambda c, d: 300e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.shares_at",
            lambda c, d: 13e9,
        )
        from skills.cvm.calculations.metrics.graham_number import graham_number_at
        assert graham_number_at("PETR4", "2024-06-30") is None

    def test_negative_pl_returns_none(self, monkeypatch):
        """Negative equity → VPA < 0 → sqrt of negative product → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.ttm_earnings_at",
            lambda c, d: 100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.pl_at",
            lambda c, d: -50e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.shares_at",
            lambda c, d: 13e9,
        )
        from skills.cvm.calculations.metrics.graham_number import graham_number_at
        assert graham_number_at("PETR4", "2024-06-30") is None

    def test_zero_shares_returns_none(self, monkeypatch):
        """Zero shares → division by zero → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.ttm_earnings_at",
            lambda c, d: 100e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.pl_at",
            lambda c, d: 300e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.shares_at",
            lambda c, d: 0,
        )
        from skills.cvm.calculations.metrics.graham_number import graham_number_at
        assert graham_number_at("PETR4", "2024-06-30") is None

    def test_none_earnings_returns_none(self, monkeypatch):
        """None earnings (missing data) → None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.ttm_earnings_at",
            lambda c, d: None,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.pl_at",
            lambda c, d: 300e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.graham_number.shares_at",
            lambda c, d: 13e9,
        )
        from skills.cvm.calculations.metrics.graham_number import graham_number_at
        assert graham_number_at("PETR4", "2024-06-30") is None

    def test_registry(self):
        """Verify graham_number is registered in the metric registry."""
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert "graham_number" in METRICS
        spec = METRICS["graham_number"]
        assert spec.ratio_key == "graham_number"
        assert spec.per_share_label is None  # fundamental ratio
        assert resolve_metric("graham_number").name == "graham_number"
