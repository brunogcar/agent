"""Tests for skills/cvm/historical/_registry.py -- central auto-discovery registry.

Verifies that:
  - Both engines and metrics are auto-discovered at import time
  - EngineSpec + MetricSpec dataclasses have all required fields
  - register_engine / register_metric populate the registries
  - resolve_metric handles canonical names + aliases
  - Duplicate registration raises ValueError
  - Auto-discovery is idempotent (re-import doesn't re-register)
"""
from __future__ import annotations

import pytest
from skills.cvm.historical._registry import (
    EngineSpec, MetricSpec, ENGINES, METRICS,
    register_engine, register_metric, resolve_metric,
    list_engines, list_metrics, list_all_metric_names,
)


# ── Engine auto-discovery tests ─────────────────────────────────────────────

class TestEngineAutoDiscovery:
    def test_price_registered(self):
        assert "price" in ENGINES

    def test_earnings_registered(self):
        assert "earnings" in ENGINES

    def test_shares_registered(self):
        assert "shares" in ENGINES

    def test_pl_registered(self):
        assert "pl" in ENGINES

    def test_dividends_registered(self):
        """New dividends engine should be auto-discovered."""
        assert "dividends" in ENGINES

    def test_price_spec(self):
        spec = ENGINES["price"]
        assert spec.name == "price"
        assert spec.quantity == "close"
        assert spec.at_fn is not None
        assert spec.periods_fn is not None
        assert "COTAHIST" in spec.source

    def test_earnings_spec(self):
        spec = ENGINES["earnings"]
        assert spec.name == "earnings"
        assert spec.quantity == "ttm"
        assert "DFP" in spec.source

    def test_dividends_spec(self):
        spec = ENGINES["dividends"]
        assert spec.name == "dividends"
        assert spec.quantity == "dpa"
        assert "B3" in spec.source

    def test_list_engines_returns_sorted(self):
        names = list_engines()
        assert names == sorted(names)
        assert "price" in names
        assert "dividends" in names


# ── Metric auto-discovery tests ─────────────────────────────────────────────

class TestMetricAutoDiscovery:
    def test_lpa_registered(self):
        assert "lpa" in METRICS

    def test_vpa_registered(self):
        assert "vpa" in METRICS

    def test_dpa_registered(self):
        """New dpa metric should be auto-discovered."""
        assert "dpa" in METRICS

    def test_lpa_spec(self):
        spec = METRICS["lpa"]
        assert spec.name == "lpa"
        assert spec.per_share_label == "LPA"
        assert spec.per_share_key == "lpa"
        assert spec.ratio_label == "P/L"
        assert spec.ratio_key == "pe"
        assert "price" in spec.engines
        assert "earnings" in spec.engines
        assert "shares" in spec.engines

    def test_dpa_spec(self):
        spec = METRICS["dpa"]
        assert spec.name == "dpa"
        assert spec.per_share_label == "DPA"
        assert spec.per_share_key == "dpa"
        assert spec.ratio_label == "Div Yield"
        assert spec.ratio_key == "dy"
        assert "price" in spec.engines
        assert "dividends" in spec.engines
        assert "earnings" in spec.engines
        assert "shares" in spec.engines
        assert "dy" in spec.aliases
        assert "payout" in spec.aliases


# ── resolve_metric tests ────────────────────────────────────────────────────

class TestResolveMetric:
    def test_canonical_name(self):
        assert resolve_metric("lpa").name == "lpa"
        assert resolve_metric("vpa").name == "vpa"
        assert resolve_metric("dpa").name == "dpa"

    def test_case_insensitive(self):
        assert resolve_metric("LPA").name == "lpa"
        assert resolve_metric("DPA").name == "dpa"

    def test_lpa_aliases(self):
        assert resolve_metric("pe").name == "lpa"
        assert resolve_metric("pl").name == "lpa"
        assert resolve_metric("p/l").name == "lpa"

    def test_vpa_aliases(self):
        assert resolve_metric("pvpa").name == "vpa"
        assert resolve_metric("p/vpa").name == "vpa"

    def test_dpa_aliases(self):
        """dy, dividend_yield, yld, payout should all resolve to dpa."""
        assert resolve_metric("dy").name == "dpa"
        assert resolve_metric("dividend_yield").name == "dpa"
        assert resolve_metric("yld").name == "dpa"
        assert resolve_metric("payout").name == "dpa"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            resolve_metric("nonexistent")

    def test_unknown_lists_available(self):
        with pytest.raises(ValueError) as exc_info:
            resolve_metric("nope")
        assert "lpa" in str(exc_info.value)
        assert "vpa" in str(exc_info.value)
        assert "dpa" in str(exc_info.value)


# ── Listing tests ────────────────────────────────────────────────────────────

class TestListing:
    def test_list_metrics_canonical_only(self):
        names = list_metrics()
        assert "lpa" in names
        assert "vpa" in names
        assert "dpa" in names
        assert "pe" not in names  # aliases not in canonical list

    def test_list_all_metric_names_includes_aliases(self):
        names = list_all_metric_names()
        assert "lpa" in names
        assert "vpa" in names
        assert "dpa" in names
        assert "pe" in names
        assert "dy" in names
        assert "payout" in names


# ── Duplicate registration tests ────────────────────────────────────────────

class TestDuplicateRegistration:
    def test_duplicate_engine_raises(self):
        with pytest.raises(ValueError, match="Duplicate engine registration"):
            register_engine(EngineSpec(
                name="price",  # already registered
                quantity="x", at_fn=lambda c, d: None,
                periods_fn=lambda c: [], source="test",
            ))

    def test_duplicate_metric_raises(self):
        with pytest.raises(ValueError, match="Duplicate metric registration"):
            register_metric(MetricSpec(
                name="lpa",  # already registered
                per_share_label="X", per_share_key="x", per_share_fn=lambda c, d: None,
                ratio_label="Y", ratio_key="y", ratio_fn=lambda c, d: None,
                history_fn=lambda c, df, dt: [], engines=[], aliases=[],
            ))

    def test_duplicate_alias_raises(self):
        with pytest.raises(ValueError, match="Alias.*conflicts"):
            register_metric(MetricSpec(
                name="custom_metric",
                per_share_label="X", per_share_key="x", per_share_fn=lambda c, d: None,
                ratio_label="Y", ratio_key="y", ratio_fn=lambda c, d: None,
                history_fn=lambda c, df, dt: [], engines=[],
                aliases=["pe"],  # already an alias for lpa
            ))
