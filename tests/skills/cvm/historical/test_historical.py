"""Tests for skills/cvm/historical/ — historical ratios skill.

Uses mocked engines + registry — no database needed.
"""
from __future__ import annotations

import pytest
from skills.cvm.historical import historical, MANIFEST, route


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_LPA_SERIES = [
    {"date": "2024-01-15", "price": 35.0, "ttm_earnings": 100e9, "shares": 13e9,
     "lpa": 100e9 / 13e9, "pe": 35.0 / (100e9 / 13e9)},
    {"date": "2024-02-15", "price": 36.0, "ttm_earnings": 100e9, "shares": 13e9,
     "lpa": 100e9 / 13e9, "pe": 36.0 / (100e9 / 13e9)},
    {"date": "2024-03-15", "price": 38.0, "ttm_earnings": 105e9, "shares": 13e9,
     "lpa": 105e9 / 13e9, "pe": 38.0 / (105e9 / 13e9)},
    {"date": "2024-04-15", "price": 37.0, "ttm_earnings": 105e9, "shares": 13e9,
     "lpa": 105e9 / 13e9, "pe": 37.0 / (105e9 / 13e9)},
    {"date": "2024-05-15", "price": 39.0, "ttm_earnings": 105e9, "shares": 13e9,
     "lpa": 105e9 / 13e9, "pe": 39.0 / (105e9 / 13e9)},
    {"date": "2024-06-15", "price": 40.0, "ttm_earnings": 110e9, "shares": 13e9,
     "lpa": 110e9 / 13e9, "pe": 40.0 / (110e9 / 13e9)},
]


def _mock_lpa_history(monkeypatch):
    """Mock lpa_history to return synthetic series.

    Patches the MetricSpec in the registry (not the module function), because
    _metric_history() calls spec.history_fn which is captured at registration time.
    """
    def fake_lpa_history(company, date_from, date_to):
        return MOCK_LPA_SERIES
    from skills.cvm.historical._registry import METRICS
    monkeypatch.setattr(METRICS["lpa"], "history_fn", fake_lpa_history)


def _mock_metric_history(monkeypatch, metric_name: str, series: list[dict]):
    """Mock a metric's history_fn in the registry. Generic helper."""
    from skills.cvm.historical._registry import METRICS
    def fake_history(company, date_from, date_to):
        return series
    monkeypatch.setattr(METRICS[metric_name], "history_fn", fake_history)


# ── Validation tests ────────────────────────────────────────────────────────

class TestValidation:
    def test_lpa_history_requires_company(self):
        r = historical.lpa_history()
        assert r["status"] == "error"

    def test_vpa_history_requires_company(self):
        r = historical.vpa_history()
        assert r["status"] == "error"

    def test_ratio_history_requires_company(self):
        r = historical.ratio_history()
        assert r["status"] == "error"

    def test_summary_requires_company(self):
        r = historical.summary()
        assert r["status"] == "error"


# ── lpa_history tests ────────────────────────────────────────────────────────

class TestLpaHistory:
    def test_basic_shape(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.lpa_history(company="PETR4", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "lpa"
        assert len(r["series"]) == 6
        # Series should have both lpa and pe keys
        assert "lpa" in r["series"][0]
        assert "pe" in r["series"][0]

    def test_has_freshness(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.lpa_history(company="PETR4")
        assert "data_freshness" in r

    def test_pe_count(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.lpa_history(company="PETR4", months=6)
        assert r["pe_days"] == 6  # all have valid PE

    def test_per_share_label_in_result(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.lpa_history(company="PETR4", months=6)
        assert r["per_share_label"] == "LPA"
        assert r["ratio_label"] == "P/L"


# ── vpa_history tests ───────────────────────────────────────────────────────

class TestVpaHistory:
    def test_requires_company(self):
        r = historical.vpa_history()
        assert r["status"] == "error"

    def test_basic_shape(self, monkeypatch):
        """vpa_history should return metric='vpa' + series with vpa + pvpa keys."""
        mock_series = [
            {"date": "2024-01-15", "price": 35.0, "pl": 300e9, "shares": 13e9,
             "vpa": 300e9 / 13e9, "pvpa": 35.0 / (300e9 / 13e9)},
            {"date": "2024-02-15", "price": 36.0, "pl": 300e9, "shares": 13e9,
             "vpa": 300e9 / 13e9, "pvpa": 36.0 / (300e9 / 13e9)},
        ]
        _mock_metric_history(monkeypatch, "vpa", mock_series)
        r = historical.vpa_history(company="PETR4", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "vpa"
        assert r["per_share_label"] == "VPA"
        assert r["ratio_label"] == "P/VPA"
        assert r["pvpa_days"] == 2
        assert len(r["series"]) == 2
        # Series should have both vpa and pvpa keys
        assert "vpa" in r["series"][0]
        assert "pvpa" in r["series"][0]


# ── ratio_history tests (generic, alias-aware) ──────────────────────────────

class TestRatioHistory:
    def test_lpa_metric(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.ratio_history(company="PETR4", metric="lpa", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "lpa"

    def test_pe_alias_resolves_to_lpa(self, monkeypatch):
        """ratio_history(metric='pe') should resolve to lpa via the alias."""
        _mock_lpa_history(monkeypatch)
        r = historical.ratio_history(company="PETR4", metric="pe", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "lpa"  # canonical name in result

    def test_pl_alias_resolves_to_lpa(self, monkeypatch):
        """ratio_history(metric='pl') should resolve to lpa via the alias."""
        _mock_lpa_history(monkeypatch)
        r = historical.ratio_history(company="PETR4", metric="pl", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "lpa"

    def test_unknown_metric(self):
        r = historical.ratio_history(company="PETR4", metric="unknown")
        assert r["status"] == "error"
        assert "Unknown metric" in r["error"]

    def test_vpa_routes_to_vpa_history(self, monkeypatch):
        """ratio_history(metric='vpa') should dispatch to vpa_history."""
        mock_series = [
            {"date": "2024-01-15", "price": 35.0, "pl": 300e9, "shares": 13e9,
             "vpa": 300e9 / 13e9, "pvpa": 35.0 / (300e9 / 13e9)},
        ]
        _mock_metric_history(monkeypatch, "vpa", mock_series)
        r = historical.ratio_history(company="PETR4", metric="vpa", months=12)
        assert r["status"] == "ok"
        assert r["metric"] == "vpa"


# ── summary tests ───────────────────────────────────────────────────────────

class TestSummary:
    def test_basic_shape(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.summary(company="PETR4")
        assert r["status"] == "ok"
        assert "current" in r
        assert "averages" in r
        assert "percentile" in r
        assert "interpretation" in r

    def test_current_has_both_per_share_and_ratio(self, monkeypatch):
        """summary current block should include both lpa (per-share) and pe (ratio)."""
        _mock_lpa_history(monkeypatch)
        r = historical.summary(company="PETR4")
        assert "lpa" in r["current"]
        assert "pe" in r["current"]
        assert "price" in r["current"]
        # Engine-specific fields
        assert "ttm_earnings" in r["current"]
        assert "shares" in r["current"]

    def test_current_pe(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.summary(company="PETR4")
        # Last entry: pe = 40 / (110e9 / 13e9) ≈ 4.727, rounded to 2 decimals
        expected_pe = round(40.0 / (110e9 / 13e9), 2)
        assert r["current"]["pe"] == pytest.approx(expected_pe, rel=1e-3)

    def test_percentile(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.summary(company="PETR4")
        assert r["percentile"] is not None
        # Current PE is the highest → 100th percentile? Let me check...
        # MOCK_LPA_SERIES PE values: 4.55, 4.68, 4.70, 4.58, 4.83, 4.73
        # sorted: [4.55, 4.58, 4.68, 4.70, 4.73, 4.83]
        # current = 4.73 → index 4 → percentile = 4/6 * 100 = 66.7
        assert r["percentile"] == 66.7

    def test_interpretation(self, monkeypatch):
        _mock_lpa_history(monkeypatch)
        r = historical.summary(company="PETR4")
        assert "expensive" in r["interpretation"] or "fair" in r["interpretation"]

    def test_summary_vpa_metric(self, monkeypatch):
        """summary(metric='vpa') should return vpa + pvpa in current block."""
        mock_vpa_series = [
            {"date": "2024-01-15", "price": 35.0, "pl": 300e9, "shares": 13e9,
             "vpa": 300e9 / 13e9, "pvpa": 35.0 / (300e9 / 13e9)},
            {"date": "2024-02-15", "price": 36.0, "pl": 300e9, "shares": 13e9,
             "vpa": 300e9 / 13e9, "pvpa": 36.0 / (300e9 / 13e9)},
            {"date": "2024-03-15", "price": 38.0, "pl": 310e9, "shares": 13e9,
             "vpa": 310e9 / 13e9, "pvpa": 38.0 / (310e9 / 13e9)},
        ]
        _mock_metric_history(monkeypatch, "vpa", mock_vpa_series)
        r = historical.summary(company="PETR4", metric="vpa")
        assert r["status"] == "ok"
        assert r["metric"] == "vpa"
        assert r["per_share_label"] == "VPA"
        assert r["ratio_label"] == "P/VPA"
        # current block should have vpa, pvpa, pl, shares, price
        assert "vpa" in r["current"]
        assert "pvpa" in r["current"]
        assert "pl" in r["current"]
        assert "shares" in r["current"]
        assert "ttm_earnings" not in r["current"]  # vpa doesn't use earnings


# ── MANIFEST auto-generation tests ───────────────────────────────────────────

class TestManifest:
    def test_lpa_history_mode_exists(self):
        assert "lpa_history" in MANIFEST["modes"]

    def test_vpa_history_mode_exists(self):
        assert "vpa_history" in MANIFEST["modes"]

    def test_generic_modes_exist(self):
        assert "ratio_history" in MANIFEST["modes"]
        assert "summary" in MANIFEST["modes"]

    def test_no_old_pe_history_mode(self):
        """Old pe_history mode should be gone (renamed to lpa_history)."""
        assert "pe_history" not in MANIFEST["modes"]


# ── Route tests ──────────────────────────────────────────────────────────────

class TestRoute:
    def test_route_no_mode_errors(self):
        r = route()
        assert r["status"] == "error"

    def test_route_unknown_mode_errors(self):
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]

    def test_route_lpa_history(self, monkeypatch):
        """route(mode='lpa_history') should dispatch correctly."""
        mock_series = [
            {"date": "2024-01-15", "price": 35.0, "ttm_earnings": 100e9,
             "shares": 13e9, "lpa": 100e9 / 13e9, "pe": 35.0 / (100e9 / 13e9)},
        ]
        _mock_metric_history(monkeypatch, "lpa", mock_series)
        r = route(mode="lpa_history", company="PETR4", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "lpa"

    def test_route_vpa_history(self, monkeypatch):
        """route(mode='vpa_history') should dispatch correctly."""
        mock_series = [
            {"date": "2024-01-15", "price": 35.0, "pl": 300e9, "shares": 13e9,
             "vpa": 300e9 / 13e9, "pvpa": 35.0 / (300e9 / 13e9)},
        ]
        _mock_metric_history(monkeypatch, "vpa", mock_series)
        r = route(mode="vpa_history", company="PETR4", months=6)
        assert r["status"] == "ok"
        assert r["metric"] == "vpa"

    def test_route_old_pe_history_fails(self):
        """Old pe_history mode should be unknown (renamed to lpa_history)."""
        r = route(mode="pe_history", company="PETR4")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]
