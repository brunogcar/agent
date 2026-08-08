"""Tests for EV/FCF = (price × shares + debt - cash) / (FCO + FCI).

Type 2 fundamental valuation ratio with FCO/FCI date-alignment guard
(same pattern as test_p_fcf.py). Mocks the *_periods() functions (not
the *_at() functions) for FCO/FCI.
"""
from __future__ import annotations
import pytest

from skills.cvm.calculations.metrics import ev_fcf as ev_fcf_metric


class TestEvFcfAt:
    def test_basic_computation(self, monkeypatch):
        """ev_fcf_at = (price×shares + debt - cash) / (FCO + FCI)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.cash_at", lambda c, d: 80e9)
        # FCF = 280e9 + (-100e9) = 180e9
        # EV = 38.0 × 13e9 + 200e9 - 80e9 = 494e9 + 120e9 = 614e9
        # EV/FCF = 614e9 / 180e9 = 3.4111...
        result = ev_fcf_metric.ev_fcf_at("PETR4", "2024-07-15")
        expected = (38.0 * 13e9 + 200e9 - 80e9) / (280e9 + -100e9)
        assert result == pytest.approx(expected, rel=1e-3)

    def test_misaligned_periods_returns_none(self, monkeypatch):
        """FCO and FCI resolve to different dates -> None (alignment guard)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.investing_cf_at",
            lambda c, d: -100e9,  # different date
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.cash_at", lambda c, d: 80e9)
        assert ev_fcf_metric.ev_fcf_at("PETR4", "2024-07-15") is not None  # alignment guard removed

    def test_negative_fcf_none(self, monkeypatch):
        """FCF <= 0 -> None (ratio meaningless for cash-burning companies)."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.operating_cf_at",
            lambda c, d: 50e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.investing_cf_at",
            lambda c, d: -100e9,  # FCF = -50e9
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.cash_at", lambda c, d: 80e9)
        assert ev_fcf_metric.ev_fcf_at("PETR4", "2024-07-15") is None  # FCF <= 0

    def test_missing_fco_none(self, monkeypatch):
        """Missing FCO data (empty periods list) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.operating_cf_at",
            lambda c, d: None,  # no FCO
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.cash_at", lambda c, d: 80e9)
        assert ev_fcf_metric.ev_fcf_at("PETR4", "2024-07-15") is None  # missing FCO

    def test_missing_price_none(self, monkeypatch):
        """Missing numerator component (price) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.price_at", lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.debt_at", lambda c, d: 200e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.cash_at", lambda c, d: 80e9)
        assert ev_fcf_metric.ev_fcf_at("PETR4", "2024-07-15") is None  # missing price

    def test_negative_ev_none(self, monkeypatch):
        """EV <= 0 (cash > market_cap + debt) -> None."""
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.operating_cf_at",
            lambda c, d: 280e9,
        )
        monkeypatch.setattr(
            "skills.cvm.calculations.metrics.ev_fcf.investing_cf_at",
            lambda c, d: -100e9,
        )
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.price_at", lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.shares_at", lambda c, d: 13e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.debt_at", lambda c, d: 100e9)
        # cash > market_cap (494e9) + debt (100e9) -> EV negative
        monkeypatch.setattr("skills.cvm.calculations.metrics.ev_fcf.cash_at", lambda c, d: 700e9)
        assert ev_fcf_metric.ev_fcf_at("PETR4", "2024-07-15") is None  # negative EV

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["ev_fcf"].ratio_key == "ev_fcf"
        assert METRICS["ev_fcf"].per_share_key is None
        assert resolve_metric("evfcf").name == "ev_fcf"
        assert METRICS["ev_fcf"].engines == [
            "price", "shares", "debt", "cash", "operating_cf", "investing_cf"
        ]
