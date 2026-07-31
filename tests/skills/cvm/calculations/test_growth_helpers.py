"""Tests for skills/cvm/calculations/growth_helpers.py.

[v1.7 review-fix] Period-specific gap-tolerance multipliers.

Pure-Python tests (no DB) — the helpers operate on pre-fetched period
lists so they can be unit-tested without a database.
"""
from __future__ import annotations

import os
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")

import pytest
from skills.cvm.calculations.growth_helpers import (
    growth_at, growth_history,
    gap_multiplier_for_lookback,
    LOOKBACK_3M, LOOKBACK_1Y, LOOKBACK_5Y,
)


# ── gap_multiplier_for_lookback ─────────────────────────────────────────────

class TestGapMultiplier:
    def test_short_lookback_uses_loose_multiplier(self):
        """3M (90d) and 1Y (365d) → 1.5 (loose)."""
        assert gap_multiplier_for_lookback(LOOKBACK_3M) == 1.5
        assert gap_multiplier_for_lookback(LOOKBACK_1Y) == 1.5

    def test_long_lookback_uses_tight_multiplier(self):
        """5Y (1825d) → 1.2 (tight)."""
        assert gap_multiplier_for_lookback(LOOKBACK_5Y) == 1.2

    def test_threshold_is_inclusive(self):
        """365 days exactly → 1.5 (short); 366 days → 1.2 (long)."""
        assert gap_multiplier_for_lookback(365) == 1.5
        assert gap_multiplier_for_lookback(366) == 1.2


# ── growth_at ────────────────────────────────────────────────────────────────

class TestGrowthAt:
    def test_basic_1y_growth(self):
        """(120 - 100) / 100 = 0.20."""
        periods = [
            {"date": "2023-12-31", "value": 100.0},
            {"date": "2024-12-31", "value": 120.0},
        ]
        assert growth_at(periods, "2024-12-31", LOOKBACK_1Y) == pytest.approx(0.20)

    def test_negative_growth(self):
        """(80 - 100) / 100 = -0.20."""
        periods = [
            {"date": "2023-12-31", "value": 100.0},
            {"date": "2024-12-31", "value": 80.0},
        ]
        assert growth_at(periods, "2024-12-31", LOOKBACK_1Y) == pytest.approx(-0.20)

    def test_negative_prior_uses_abs(self):
        """Prior = -100, curr = 50 → (50 - (-100)) / |-100| = 1.5."""
        periods = [
            {"date": "2023-12-31", "value": -100.0},
            {"date": "2024-12-31", "value": 50.0},
        ]
        assert growth_at(periods, "2024-12-31", LOOKBACK_1Y) == pytest.approx(1.5)

    def test_zero_prior_returns_none(self):
        """Division by zero → None."""
        periods = [
            {"date": "2023-12-31", "value": 0.0},
            {"date": "2024-12-31", "value": 100.0},
        ]
        assert growth_at(periods, "2024-12-31", LOOKBACK_1Y) is None

    def test_missing_prior_returns_none(self):
        """No period within the gap window → None."""
        periods = [
            {"date": "2024-12-31", "value": 100.0},
        ]
        assert growth_at(periods, "2024-12-31", LOOKBACK_1Y) is None

    def test_gap_tolerance_bridges_missing_year(self):
        """[period-specific gap tolerance] A 5Y lookback with 1.2x tolerance
        accepts a period ~5.5 years back (within the [4.17Y, 6.0Y] window).

        The symmetric tolerance window is [lookback/mult, lookback*mult]:
          5Y (1825d), 1.2x → [1521d, 2190d] = [4.17Y, 6.0Y]

        A period 2 years back is TOO CLOSE (730d < 1521d) and is rejected.
        A period ~5.5 years back (~2008d) is within the window and accepted.
        """
        periods = [
            {"date": "2019-06-30", "value": 100.0},  # ~5.5Y back (2008d)
            {"date": "2024-12-31", "value": 150.0},  # latest
        ]
        # 1Y: 2008 days apart >> 547-day max → None
        assert growth_at(periods, "2024-12-31", LOOKBACK_1Y) is None
        # 5Y: 2008 days apart is within [1521, 2190] → bridges (growth = 0.50)
        assert growth_at(periods, "2024-12-31", LOOKBACK_5Y) == pytest.approx(0.50)

    def test_gap_tolerance_1y_bridges_offcycle_filing(self):
        """1Y lookback (1.5x = 547-day window) bridges a ~15-month-off prior.

        The symmetric window for 1Y (365d, 1.5x) is [243d, 547d].
        A prior 15 months back (~456d) is within this window.
        """
        periods = [
            {"date": "2023-09-30", "value": 100.0},  # ~15 months before 2024-12-31
            {"date": "2024-12-31", "value": 110.0},
        ]
        result = growth_at(periods, "2024-12-31", LOOKBACK_1Y)
        assert result is not None
        assert result == pytest.approx(0.10)

    def test_5y_tight_tolerance_rejects_7y_gap(self):
        """5Y lookback (1.2x = 2190-day max) rejects a 7Y gap (~2555 days)."""
        periods = [
            {"date": "2017-12-31", "value": 50.0},  # 7 years before 2024-12-31
            {"date": "2024-12-31", "value": 200.0},
        ]
        # 7 years = ~2555 days > 2190 → rejected
        assert growth_at(periods, "2024-12-31", LOOKBACK_5Y) is None

    def test_5y_rejects_period_too_close(self):
        """5Y lookback rejects a period only 2 years back (too close).

        2 years = ~731 days < 1521d (the min of the 1.2x window) → rejected.
        This prevents computing "5Y growth" from a 2Y-old baseline.
        """
        periods = [
            {"date": "2022-12-31", "value": 100.0},  # 2Y back — too close for 5Y
            {"date": "2024-12-31", "value": 150.0},
        ]
        assert growth_at(periods, "2024-12-31", LOOKBACK_5Y) is None

    def test_5y_accepts_5y_exact(self):
        """5Y lookback accepts a period exactly 5 years back."""
        periods = [
            {"date": "2019-12-31", "value": 100.0},  # exactly 5Y before 2024-12-31
            {"date": "2024-12-31", "value": 200.0},
        ]
        result = growth_at(periods, "2024-12-31", LOOKBACK_5Y)
        assert result == pytest.approx(1.0)  # (200-100)/100

    def test_none_value_period_skipped(self):
        """A period with value=None is skipped; the next-best within the
        tolerance window is used instead."""
        periods = [
            {"date": "2019-12-31", "value": None},   # 5Y back but missing
            {"date": "2019-06-30", "value": 100.0},  # ~5.5Y back — within 5Y window
            {"date": "2024-12-31", "value": 120.0},
        ]
        # 5Y: 2019-12-31 is None (skipped), 2019-06-30 is ~2008d back (within
        # [1521, 2190]) → growth = (120-100)/100 = 0.20
        assert growth_at(periods, "2024-12-31", LOOKBACK_5Y) == pytest.approx(0.20)

    def test_empty_periods(self):
        assert growth_at([], "2024-12-31", LOOKBACK_1Y) is None

    def test_no_period_on_or_before_target(self):
        """All periods after target → None."""
        periods = [{"date": "2025-06-30", "value": 100.0}]
        assert growth_at(periods, "2024-12-31", LOOKBACK_1Y) is None


# ── growth_history ───────────────────────────────────────────────────────────

class TestGrowthHistory:
    def test_basic_shape(self):
        periods = [
            {"date": "2020-12-31", "value": 100.0},
            {"date": "2021-12-31", "value": 110.0},
            {"date": "2022-12-31", "value": 121.0},
            {"date": "2023-12-31", "value": 133.1},
        ]
        hist = growth_history(periods, LOOKBACK_1Y)
        assert len(hist) == 4
        # First entry has no prior (within 1Y window) → growth=None
        assert hist[0]["growth"] is None
        # 2021 vs 2020 → 0.10
        assert hist[1]["growth"] == pytest.approx(0.10)
        assert hist[1]["prior_date"] == "2020-12-31"
        # 2022 vs 2021 → 0.10
        assert hist[2]["growth"] == pytest.approx(0.10)

    def test_returns_prior_date(self):
        """The prior_date field lets callers see WHICH period was the baseline."""
        periods = [
            {"date": "2020-12-31", "value": 100.0},
            {"date": "2021-12-31", "value": 120.0},
        ]
        hist = growth_history(periods, LOOKBACK_1Y)
        assert hist[1]["prior_date"] == "2020-12-31"
        assert hist[0]["prior_date"] is None  # no prior for first entry

    def test_date_range_filter(self):
        periods = [
            {"date": "2020-12-31", "value": 100.0},
            {"date": "2021-12-31", "value": 110.0},
            {"date": "2022-12-31", "value": 121.0},
        ]
        hist = growth_history(periods, LOOKBACK_1Y, date_from="2021-01-01")
        assert len(hist) == 2  # 2021 + 2022 only

    def test_empty_periods(self):
        assert growth_history([], LOOKBACK_1Y) == []
