"""Tests for skills/cvm/historical/metrics/_registry.py -- metric auto-discovery.

Verifies that:
  - Metric modules are auto-discovered at import time
  - MetricSpec dataclass has all required fields
  - register_metric populates METRICS + _ALIASES
  - resolve_metric handles canonical names + aliases
  - Duplicate registration raises ValueError
"""
from __future__ import annotations

import pytest
from skills.cvm.historical.metrics._registry import (
    MetricSpec, METRICS, register_metric, resolve_metric,
    list_metrics, list_all_names, _ALIASES,
)


# ── Auto-discovery tests ────────────────────────────────────────────────────

class TestAutoDiscovery:
    def test_lpa_registered(self):
        """lpa metric should be auto-discovered and registered."""
        assert "lpa" in METRICS

    def test_vpa_registered(self):
        """vpa metric should be auto-discovered and registered."""
        assert "vpa" in METRICS

    def test_lpa_has_correct_spec(self):
        spec = METRICS["lpa"]
        assert spec.name == "lpa"
        assert spec.per_share_label == "LPA"
        assert spec.per_share_key == "lpa"
        assert spec.ratio_label == "P/L"
        assert spec.ratio_key == "pe"
        assert "price" in spec.engines
        assert "earnings" in spec.engines
        assert "shares" in spec.engines

    def test_vpa_has_correct_spec(self):
        spec = METRICS["vpa"]
        assert spec.name == "vpa"
        assert spec.per_share_label == "VPA"
        assert spec.per_share_key == "vpa"
        assert spec.ratio_label == "P/VPA"
        assert spec.ratio_key == "pvpa"
        assert "price" in spec.engines
        assert "pl" in spec.engines
        assert "shares" in spec.engines


# ── resolve_metric tests ────────────────────────────────────────────────────

class TestResolveMetric:
    def test_canonical_name(self):
        assert resolve_metric("lpa").name == "lpa"
        assert resolve_metric("vpa").name == "vpa"

    def test_case_insensitive(self):
        assert resolve_metric("LPA").name == "lpa"
        assert resolve_metric("VPA").name == "vpa"

    def test_lpa_aliases(self):
        """pe, pl, p/l should all resolve to lpa."""
        assert resolve_metric("pe").name == "lpa"
        assert resolve_metric("pl").name == "lpa"
        assert resolve_metric("p/l").name == "lpa"

    def test_vpa_aliases(self):
        """pvpa, p/vpa should all resolve to vpa."""
        assert resolve_metric("pvpa").name == "vpa"
        assert resolve_metric("p/vpa").name == "vpa"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            resolve_metric("nonexistent")

    def test_unknown_lists_available(self):
        """Error message should list available metrics."""
        with pytest.raises(ValueError) as exc_info:
            resolve_metric("nope")
        assert "lpa" in str(exc_info.value)
        assert "vpa" in str(exc_info.value)


# ── list_metrics / list_all_names tests ─────────────────────────────────────

class TestListing:
    def test_list_metrics_canonical_only(self):
        names = list_metrics()
        assert "lpa" in names
        assert "vpa" in names
        assert "pe" not in names  # aliases not in canonical list
        assert "pvpa" not in names

    def test_list_all_names_includes_aliases(self):
        names = list_all_names()
        assert "lpa" in names
        assert "vpa" in names
        assert "pe" in names     # aliases included
        assert "pl" in names
        assert "p/l" in names
        assert "pvpa" in names
        assert "p/vpa" in names


# ── register_metric tests ───────────────────────────────────────────────────

class TestRegisterMetric:
    def test_duplicate_name_raises(self):
        """Registering the same name twice should raise."""
        with pytest.raises(ValueError, match="Duplicate metric registration"):
            register_metric(MetricSpec(
                name="lpa",  # already registered
                per_share_label="X", per_share_key="x", per_share_fn=lambda c, d: None,
                ratio_label="Y", ratio_key="y", ratio_fn=lambda c, d: None,
                history_fn=lambda c, df, dt: [], engines=[], aliases=[],
            ))

    def test_duplicate_alias_raises(self):
        """Registering an alias that's already taken should raise."""
        with pytest.raises(ValueError, match="Alias.*conflicts"):
            register_metric(MetricSpec(
                name="custom_metric",
                per_share_label="X", per_share_key="x", per_share_fn=lambda c, d: None,
                ratio_label="Y", ratio_key="y", ratio_fn=lambda c, d: None,
                history_fn=lambda c, df, dt: [], engines=[],
                aliases=["pe"],  # already an alias for lpa
            ))
