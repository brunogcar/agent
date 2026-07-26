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

    def test_ev_ebitda_not_implemented(self):
        # ev_ebitda is still a stub — should return error (not implemented)
        r = historical.ratio_history(company="PETR4", metric="ev_ebitda")
        assert r["status"] == "error"
        assert "Unknown metric" in r["error"]

    def test_vpa_routes_to_vpa_history(self, monkeypatch):
        """ratio_history(metric='vpa') should dispatch to vpa_history."""
        called = {}
        def fake_vpa_history(company, months):
            called["company"] = company
            called["months"] = months
            return {"status": "ok", "company": company, "metric": "vpa",
                    "total_days": 1, "vpa_days": 1, "series": []}
        monkeypatch.setattr(
            "skills.cvm.historical.historical.vpa_history", fake_vpa_history
        )
        r = historical.ratio_history(company="PETR4", metric="vpa", months=12)
        assert r["status"] == "ok"
        assert called["company"] == "PETR4"
        assert called["months"] == 12


class TestVpaHistory:
    def test_requires_company(self):
        r = historical.vpa_history()
        assert r["status"] == "error"

    def test_basic_shape(self, monkeypatch):
        """vpa_history should return metric='vpa' + series from the vpa engine."""
        mock_series = [
            {"date": "2024-01-15", "price": 35.0, "pl": 300e9, "shares": 13e9, "vpa": 35.0 * 13e9 / 300e9},
            {"date": "2024-02-15", "price": 36.0, "pl": 300e9, "shares": 13e9, "vpa": 36.0 * 13e9 / 300e9},
        ]
        def fake_vpa_history(company, date_from, date_to):
            return mock_series
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.vpa_history", fake_vpa_history
        )
        r = historical.vpa_history(company="PETR4", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "vpa"
        assert r["vpa_days"] == 2
        assert len(r["series"]) == 2


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

    def test_summary_vpa_metric(self, monkeypatch):
        """summary(metric='vpa') should return metric='vpa' + pl/shares in current."""
        mock_vpa_series = [
            {"date": "2024-01-15", "price": 35.0, "pl": 300e9, "shares": 13e9,
             "vpa": 35.0 * 13e9 / 300e9},
            {"date": "2024-02-15", "price": 36.0, "pl": 300e9, "shares": 13e9,
             "vpa": 36.0 * 13e9 / 300e9},
            {"date": "2024-03-15", "price": 38.0, "pl": 310e9, "shares": 13e9,
             "vpa": 38.0 * 13e9 / 310e9},
        ]
        def fake_vpa_history(company, date_from, date_to):
            return mock_vpa_series
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.vpa_history", fake_vpa_history
        )
        r = historical.summary(company="PETR4", metric="vpa")
        assert r["status"] == "ok"
        assert r["metric"] == "vpa"
        # current block should have vpa, pl, shares, price (no ttm_earnings)
        assert "vpa" in r["current"]
        assert "pl" in r["current"]
        assert "shares" in r["current"]
        assert "ttm_earnings" not in r["current"]
        # Last VPA = 38 * 13e9 / 310e9 ≈ 1.5935, rounded to 2 decimals = 1.59
        assert r["current"]["vpa"] == pytest.approx(
            round(38 * 13e9 / 310e9, 2), rel=1e-3
        )


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

    def test_route_vpa_history(self, monkeypatch):
        """route(mode='vpa_history') should dispatch correctly."""
        from skills.cvm.historical import route
        mock_series = [
            {"date": "2024-01-15", "price": 35.0, "pl": 300e9, "shares": 13e9, "vpa": 1.5},
        ]
        def fake_vpa_history(company, date_from, date_to):
            return mock_series
        monkeypatch.setattr(
            "skills.cvm.historical.metrics.vpa.vpa_history", fake_vpa_history
        )
        r = route(mode="vpa_history", company="PETR4", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "vpa"
