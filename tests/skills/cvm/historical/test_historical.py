"""Tests for skills/cvm/historical/ — historical ratios skill.

Uses mocked engines (price, earnings, shares) — no database needed.
"""
from __future__ import annotations

import pytest
from skills.cvm.historical import historical


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_SERIES = [
    {"date": "2024-01-15", "price": 35.0, "ttm_earnings": 100e9, "shares": 13e9, "pe": 35.0 * 13e9 / 100e9},
    {"date": "2024-02-15", "price": 36.0, "ttm_earnings": 100e9, "shares": 13e9, "pe": 36.0 * 13e9 / 100e9},
    {"date": "2024-03-15", "price": 38.0, "ttm_earnings": 105e9, "shares": 13e9, "pe": 38.0 * 13e9 / 105e9},
    {"date": "2024-04-15", "price": 37.0, "ttm_earnings": 105e9, "shares": 13e9, "pe": 37.0 * 13e9 / 105e9},
    {"date": "2024-05-15", "price": 39.0, "ttm_earnings": 105e9, "shares": 13e9, "pe": 39.0 * 13e9 / 105e9},
    {"date": "2024-06-15", "price": 40.0, "ttm_earnings": 110e9, "shares": 13e9, "pe": 40.0 * 13e9 / 110e9},
]


def _mock_pe_history(monkeypatch):
    """Mock pe_history to return synthetic series."""
    def fake_pe_history(company, date_from, date_to):
        return MOCK_SERIES
    monkeypatch.setattr("skills.cvm.historical.metrics.pe.pe_history", fake_pe_history)


class TestValidation:
    def test_pe_history_requires_company(self):
        r = historical.pe_history()
        assert r["status"] == "error"

    def test_ratio_history_requires_company(self):
        r = historical.ratio_history()
        assert r["status"] == "error"

    def test_summary_requires_company(self):
        r = historical.summary()
        assert r["status"] == "error"


class TestPeHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.pe_history(company="PETR4", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "pe"
        assert len(r["series"]) == 6
        assert "pe" in r["series"][0]

    def test_has_freshness(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.pe_history(company="PETR4")
        assert "data_freshness" in r

    def test_pe_count(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.pe_history(company="PETR4", months=6)
        assert r["pe_days"] == 6  # all have valid PE


class TestRatioHistory:
    def test_pe_metric(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.ratio_history(company="PETR4", metric="pe", months=6)
        assert r["status"] == "ok"

    def test_unknown_metric(self):
        r = historical.ratio_history(company="PETR4", metric="unknown")
        assert r["status"] == "error"

    def test_pvpa_not_implemented(self):
        r = historical.ratio_history(company="PETR4", metric="pvpa")
        assert r["status"] == "not_implemented"


class TestSummary:
    def test_basic_shape(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.summary(company="PETR4")
        assert r["status"] == "ok"
        assert "current" in r
        assert "averages" in r
        assert "percentile" in r
        assert "interpretation" in r

    def test_current_pe(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.summary(company="PETR4")
        # Last entry in MOCK_SERIES: pe = 40 * 13e9 / 110e9 ≈ 4.727
        assert r["current"]["pe"] == pytest.approx(40 * 13e9 / 110e9, rel=1e-3)

    def test_percentile(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.summary(company="PETR4")
        # Current PE (4.727) is at index 4 of 6 sorted values → 66.7th percentile
        assert r["percentile"] is not None
        assert r["percentile"] == 66.7

    def test_interpretation(self, monkeypatch):
        _mock_pe_history(monkeypatch)
        r = historical.summary(company="PETR4")
        assert "expensive" in r["interpretation"] or "fair" in r["interpretation"]


class TestRoute:
    def test_route_no_mode_errors(self):
        from skills.cvm.historical import route
        r = route()
        assert r["status"] == "error"

    def test_route_unknown_mode_errors(self):
        from skills.cvm.historical import route
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]
