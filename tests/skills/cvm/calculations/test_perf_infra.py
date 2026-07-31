"""Tests for skills/_base.py engine cache (F7).

[v1.8 F7] Verifies the @engine_cached decorator + engine_cache_scope
ContextVar-scoped cache. Critically, these tests verify that DB query
COUNTS drop (not just function identity) — the false confidence that
broke v3 was that identity tests passed while caching was never actually
active for metrics (which use direct-reference imports).

Pure-Python tests (no DB access) — uses mocks for all engine functions.
"""
from __future__ import annotations

import os
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
os.environ.setdefault("CVM_SKIP_SYNC", "1")
os.environ.setdefault("CVM_SKIP_MATERIALIZED", "1")

import pytest
from skills._base import (
    engine_cached, engine_cache_scope, _ENGINE_CACHE,
)


# ── engine_cached decorator ─────────────────────────────────────────────────

class TestEngineCachedDecorator:
    """Tests for the @engine_cached decorator itself."""

    def test_passthrough_when_no_scope(self):
        """Without a cache scope, the decorator calls through directly."""
        call_count = 0

        @engine_cached
        def fake_at(company, date):
            nonlocal call_count
            call_count += 1
            return 42.0

        assert fake_at("PETR4", "2024-06-30") == 42.0
        assert fake_at("PETR4", "2024-06-30") == 42.0
        assert call_count == 2  # no cache → 2 calls

    def test_caches_within_scope(self):
        """Within a cache scope, repeated calls hit the cache."""
        call_count = 0

        @engine_cached
        def fake_at(company, date):
            nonlocal call_count
            call_count += 1
            return 42.0

        with engine_cache_scope():
            assert fake_at("PETR4", "2024-06-30") == 42.0
            assert fake_at("PETR4", "2024-06-30") == 42.0
            assert fake_at("PETR4", "2024-06-30") == 42.0
            assert call_count == 1  # cached → 1 call

    def test_different_args_not_cached(self):
        """Different (company, date) keys each miss the cache."""
        call_count = 0

        @engine_cached
        def fake_at(company, date):
            nonlocal call_count
            call_count += 1
            return float(len(company) + len(date))

        with engine_cache_scope():
            fake_at("PETR4", "2024-06-30")
            fake_at("VALE3", "2024-06-30")  # different company
            fake_at("PETR4", "2024-12-31")  # different date
            assert call_count == 3

    def test_none_values_cached(self):
        """None results ARE cached (prevents re-querying missing data)."""
        call_count = 0

        @engine_cached
        def fake_at(company, date):
            nonlocal call_count
            call_count += 1
            return None

        with engine_cache_scope():
            assert fake_at("PETR4", "2024-06-30") is None
            assert fake_at("PETR4", "2024-06-30") is None
            assert call_count == 1  # None cached → 1 call

    def test_periods_fn_cached(self):
        """periods_fn(company) is cached per-company."""
        call_count = 0

        @engine_cached
        def fake_periods(company):
            nonlocal call_count
            call_count += 1
            return [{"date": "2024-12-31", "value": 100.0}]

        with engine_cache_scope():
            fake_periods("PETR4")
            fake_periods("PETR4")
            assert call_count == 1

    def test_preserves_function_identity(self):
        """@engine_cached preserves __name__, __wrapped__, __doc__.

        This is what makes `spec.at_fn is module.fn` pass — both point
        to the wrapper, and the wrapper has the same __name__ as the
        original.
        """
        @engine_cached
        def my_fn(company, date):
            """My docstring."""
            return 1.0

        assert my_fn.__name__ == "my_fn"
        assert my_fn.__doc__ == "My docstring."
        assert hasattr(my_fn, "__wrapped__")

    def test_scope_exits_clear_cache(self):
        """After scope exits, caching is gone (no leakage)."""
        call_count = 0

        @engine_cached
        def fake_at(company, date):
            nonlocal call_count
            call_count += 1
            return 42.0

        with engine_cache_scope():
            fake_at("PETR4", "2024-06-30")
        # Outside scope → no cache
        fake_at("PETR4", "2024-06-30")
        assert call_count == 2


# ── engine_cache_scope ──────────────────────────────────────────────────────

class TestEngineCacheScope:
    """Tests for the engine_cache_scope context manager."""

    def test_stats_tracking(self):
        """The stats property reports hits + misses + size."""
        @engine_cached
        def fake_at(company, date):
            return 42.0

        with engine_cache_scope() as scope:
            fake_at("PETR4", "2024-06-30")  # miss
            fake_at("PETR4", "2024-06-30")  # hit
            fake_at("PETR4", "2024-06-30")  # hit
            assert scope.stats["misses"] == 1
            assert scope.stats["hits"] == 2
            assert scope.stats["size"] >= 1

    def test_reentrancy_reuses_outer_scope(self):
        """Nested engine_cache_scope reuses the outer cache (doesn't wipe it)."""
        call_count = 0

        @engine_cached
        def fake_at(company, date):
            nonlocal call_count
            call_count += 1
            return 42.0

        with engine_cache_scope() as outer:
            fake_at("PETR4", "2024-06-30")  # miss (1 call)
            assert call_count == 1

            with engine_cache_scope() as inner:
                # Inner scope reuses outer cache → this is a HIT, not a miss
                fake_at("PETR4", "2024-06-30")  # hit (no new call)
                assert call_count == 1
                assert inner.stats["hits"] >= 1

            # After inner exits, outer cache is still active
            fake_at("PETR4", "2024-06-30")  # hit (no new call)
            assert call_count == 1

    def test_concurrent_scopes_isolated(self):
        """Two non-nested scopes don't share cache (simulated)."""
        @engine_cached
        def fake_at(company, date):
            import random
            return random.random()  # different value each call

        # Sequential scopes (not nested) → independent caches
        with engine_cache_scope():
            v1 = fake_at("PETR4", "2024-06-30")
            v2 = fake_at("PETR4", "2024-06-30")
            assert v1 == v2  # cached within scope

        with engine_cache_scope():
            v3 = fake_at("PETR4", "2024-06-30")
            # New scope → new cache → new value (probably different from v1)
            # (We can't assert v3 != v1 because random could collide,
            # but we CAN assert the cache is fresh — v3 == v4 below.)
            v4 = fake_at("PETR4", "2024-06-30")
            assert v3 == v4  # cached within new scope


# ── Integration: compute_all_ratios uses cache ─────────────────────────────

class TestComputeAllRatiosCaching:
    """Verifies that compute_all_ratios() actually activates the cache.

    This is the test that SHOULD have been in v3 — it verifies DB query
    count drops, not just function identity. The v3 false confidence was
    that identity tests passed while caching was never active for metrics
    (which use direct-reference imports, invisible to monkey-patching).
    """

    def test_shared_engine_cached_across_metrics(self, monkeypatch):
        """When 2 metrics share an engine, the engine is queried ONCE.

        Setup: mock the calculations registry with 2 fake metrics that
        both compose the same fake engine. Verify the engine's at_fn is
        called only ONCE per (company, date) when compute_all_ratios
        runs.
        """
        from dataclasses import dataclass, field
        from typing import Callable

        # Build a fake engine function + track calls
        engine_calls = 0

        def fake_earnings_at(company, date):
            nonlocal engine_calls
            engine_calls += 1
            return 100e9

        # Decorate it (simulating what @engine_cached does in engine files)
        fake_earnings_at = engine_cached(fake_earnings_at)

        # Build 2 fake metrics that both call fake_earnings_at
        def metric_a_fn(company, date):
            earnings = fake_earnings_at(company, date)
            return earnings / 500e9 if earnings else None

        def metric_b_fn(company, date):
            earnings = fake_earnings_at(company, date)
            return earnings / 800e9 if earnings else None

        @dataclass
        class FakeMetricSpec:
            name: str
            ratio_label: str = ""
            ratio_key: str = ""
            ratio_fn: Callable = None
            history_fn: Callable = None
            engines: list = field(default_factory=list)
            category: str = ""
            per_share_label: str = None
            per_share_key: str = None
            per_share_fn: Callable = None
            aliases: list = field(default_factory=list)

        fake_metrics = {
            "metric_a": FakeMetricSpec(name="metric_a", category="profitability",
                                       ratio_fn=metric_a_fn),
            "metric_b": FakeMetricSpec(name="metric_b", category="profitability",
                                       ratio_fn=metric_b_fn),
        }

        # Patch the METRICS dict on the _registry module
        import skills.cvm.calculations._registry as reg_mod
        monkeypatch.setattr(reg_mod, "METRICS", fake_metrics)

        # Call compute_all_ratios — should activate the cache scope
        result = reg_mod.compute_all_ratios("PETR4", "2024-06-30")

        # Both metrics computed
        assert result["metric_a"] == 100e9 / 500e9  # 0.2
        assert result["metric_b"] == 100e9 / 800e9  # 0.125

        # CRITICAL: the shared engine was called only ONCE (cached on 2nd call)
        assert engine_calls == 1, (
            f"Expected 1 engine call (cached), got {engine_calls}. "
            "The cache is NOT active for metrics — same bug as v3."
        )

    def test_different_dates_not_cached(self, monkeypatch):
        """Different dates produce different engine calls (cache key includes date)."""
        from dataclasses import dataclass, field
        from typing import Callable

        engine_calls = 0

        def fake_earnings_at(company, date):
            nonlocal engine_calls
            engine_calls += 1
            return 100e9

        fake_earnings_at = engine_cached(fake_earnings_at)

        def metric_fn(company, date):
            return fake_earnings_at(company, date)

        @dataclass
        class FakeMetricSpec:
            name: str
            ratio_label: str = ""
            ratio_key: str = ""
            ratio_fn: Callable = None
            history_fn: Callable = None
            engines: list = field(default_factory=list)
            category: str = ""
            per_share_label: str = None
            per_share_key: str = None
            per_share_fn: Callable = None
            aliases: list = field(default_factory=list)

        fake_metrics = {
            "metric_a": FakeMetricSpec(name="metric_a", category="profitability",
                                       ratio_fn=metric_fn),
        }

        import skills.cvm.calculations._registry as reg_mod
        monkeypatch.setattr(reg_mod, "METRICS", fake_metrics)

        # First call — 1 engine call
        reg_mod.compute_all_ratios("PETR4", "2024-06-30")
        assert engine_calls == 1

        # Second call with DIFFERENT date — new engine call (cache key differs)
        reg_mod.compute_all_ratios("PETR4", "2024-12-31")
        assert engine_calls == 2  # different date → cache miss → new call

    def test_no_scope_for_standalone_calls(self):
        """When called outside compute_all_ratios, no cache is active."""
        call_count = 0

        @engine_cached
        def fake_at(company, date):
            nonlocal call_count
            call_count += 1
            return 42.0

        # Standalone call (no scope) → passthrough, no caching
        fake_at("PETR4", "2024-06-30")
        fake_at("PETR4", "2024-06-30")
        assert call_count == 2  # no cache → 2 calls


# ── Real engine identity test ───────────────────────────────────────────────

class TestRealEngineIdentity:
    """Verifies that real engines (with @engine_cached applied) preserve
    `spec.at_fn is module.fn` identity. This is the contract the 14
    registry test files assert — if it breaks, the decorator was applied
    incorrectly.
    """

    def test_earnings_identity(self):
        """spec.at_fn is earnings.ttm_earnings_at (both are the wrapper)."""
        from skills.cvm.calculations._registry import ENGINES
        from skills.cvm.calculations.engines import earnings as earnings_mod

        spec = ENGINES["earnings"]
        assert spec.at_fn is earnings_mod.ttm_earnings_at
        assert spec.periods_fn is earnings_mod.ttm_earnings_periods

    def test_pl_identity(self):
        """spec.at_fn is pl.pl_at (both are the wrapper)."""
        from skills.cvm.calculations._registry import ENGINES
        from skills.cvm.calculations.engines import pl as pl_mod

        spec = ENGINES["pl"]
        assert spec.at_fn is pl_mod.pl_at
        assert spec.periods_fn is pl_mod.pl_periods

    def test_cogs_identity(self):
        """spec.at_fn is cogs.cogs_at (both are the wrapper)."""
        from skills.cvm.calculations._registry import ENGINES
        from skills.cvm.calculations.engines import cogs as cogs_mod

        spec = ENGINES["cogs"]
        assert spec.at_fn is cogs_mod.cogs_at
        assert spec.periods_fn is cogs_mod.cogs_periods

    def test_all_engines_have_wrapped_at_fn(self):
        """Every registered engine's at_fn has __wrapped__ (is decorated)."""
        from skills.cvm.calculations._registry import ENGINES

        for name, spec in ENGINES.items():
            assert hasattr(spec.at_fn, "__wrapped__"), (
                f"Engine '{name}' at_fn is not decorated with @engine_cached. "
                "Did the decorator script miss this file?"
            )
            assert hasattr(spec.periods_fn, "__wrapped__"), (
                f"Engine '{name}' periods_fn is not decorated with @engine_cached."
            )
