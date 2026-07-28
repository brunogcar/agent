"""Tests for Price to Tangible Book metric.

Type 1 metric (per-share + ratio):
  - Tangible Book / Ação = (PL - Intangibles) / shares
  - P/Tangible Book = price / Tangible Book / Ação

Guards:
  - PL > 0
  - shares > 0
  - intangibles is not None (do not silently substitute 0)
  - (PL - Intangibles) > 0 (tangible equity > 0)
  - Tangible Book per Share > 0
"""
from __future__ import annotations

import pytest

from skills.cvm.calculations.metrics import price_to_tangible_book as ptb_metric


class TestPriceToTangibleBookAt:
    def test_basic_computation(self, monkeypatch):
        """Tangible Book/Ação = (PL - Intangibles)/shares; P/TB = price/TB_ps."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        # Tangible equity = 350 - 50 = 300e9
        # Tangible Book/Ação = 300e9 / 13e9 = 23.0769...
        # P/TB = 38.0 / 23.0769... = 1.6466...
        result_ratio = ptb_metric.p_tangible_book_at("PETR4", "2024-06-30")
        assert result_ratio == pytest.approx(38.0 / ((350e9 - 50e9) / 13e9), rel=1e-3)

    def test_tangible_book_per_share(self, monkeypatch):
        """tangible_book_ps_at = (PL - Intangibles) / shares."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        result = ptb_metric.tangible_book_ps_at("PETR4", "2024-06-30")
        assert result == pytest.approx((350e9 - 50e9) / 13e9, rel=1e-3)

    def test_missing_price_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None

    def test_zero_price_none(self, monkeypatch):
        """Zero price -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None

    def test_missing_pl_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None

    def test_negative_pl_none(self, monkeypatch):
        """Negative equity -> None (tangible_book_ps_at returns None)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: -50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 10e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None

    def test_missing_intangibles_none(self, monkeypatch):
        """Missing intangibles -> None (do not silently substitute 0)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: None)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None
        assert ptb_metric.tangible_book_ps_at("PETR4", "2024-06-30") is None

    def test_missing_shares_none(self, monkeypatch):
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: None)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None

    def test_zero_shares_none(self, monkeypatch):
        """Zero shares -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 0)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None

    def test_intangibles_exceed_pl_none(self, monkeypatch):
        """Intangibles > PL -> negative tangible equity -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 80e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None
        assert ptb_metric.tangible_book_ps_at("PETR4", "2024-06-30") is None

    def test_intangibles_equal_pl_none(self, monkeypatch):
        """Intangibles == PL -> zero tangible equity -> None."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 50e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        assert ptb_metric.p_tangible_book_at("PETR4", "2024-06-30") is None
        assert ptb_metric.tangible_book_ps_at("PETR4", "2024-06-30") is None

    def test_zero_intangibles_equivalent_to_vpa(self, monkeypatch):
        """Zero intangibles -> Tangible Book = PL (same as VPA)."""
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.price_at",
                            lambda c, d: 38.0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.pl_at",
                            lambda c, d: 350e9)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.intangibles_at",
                            lambda c, d: 0)
        monkeypatch.setattr("skills.cvm.calculations.metrics.price_to_tangible_book.shares_at",
                            lambda c, d: 13e9)
        # Tangible Book/Ação = 350e9 / 13e9 = 26.923...
        # P/TB = 38.0 / 26.923 = 1.411...
        result_ps = ptb_metric.tangible_book_ps_at("PETR4", "2024-06-30")
        assert result_ps == pytest.approx(350e9 / 13e9, rel=1e-3)
        result_ratio = ptb_metric.p_tangible_book_at("PETR4", "2024-06-30")
        assert result_ratio == pytest.approx(38.0 / (350e9 / 13e9), rel=1e-3)

    def test_registry(self):
        from skills.cvm.calculations._registry import METRICS, resolve_metric
        assert METRICS["price_to_tangible_book"].ratio_key == "p_tangible_book"
        assert METRICS["price_to_tangible_book"].per_share_key == "tangible_book_ps"
        assert METRICS["price_to_tangible_book"].per_share_label == "VPA Tangível"
        assert METRICS["price_to_tangible_book"].ratio_label == "P/VPA Tangível"
        assert resolve_metric("p_vpa_tangivel").name == "price_to_tangible_book"
        assert resolve_metric("ptb").name == "price_to_tangible_book"
        assert resolve_metric("price_tangible_book").name == "price_to_tangible_book"
