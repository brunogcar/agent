"""tests/data_sources/test_meses.py -- Tests for _meses.compute_meses + helpers.

These tests mirror rapinav2's test suite (pkg/contabil/contabil_cvm_dfp_test.go:80-164)
to verify our Python implementation matches the original Go logic exactly.

The meses computation is THE critical fix — the old implementation had an off-by-one
error, bucketed 15→12, and didn't handle BPA/BPP snapshots correctly.
"""

from __future__ import annotations

import pytest

from data_sources.cvm._meses import (
    compute_meses,
    is_snapshot,
    is_flow,
    should_keep_row,
    is_valid_meses,
)


# ===========================================================================
# compute_meses — mirrors rapinav2's monthsDiff test cases
# ===========================================================================


class TestComputeMeses:
    """Test meses computation against rapinav2's test suite."""

    def test_bpa_bpp_snapshot_empty_dt_ini(self):
        """BPA/BPP rows have DT_INI_EXERC="" → meses=12 (snapshot)."""
        assert compute_meses("", "2023-12-31") == 12
        assert compute_meses("", "2023-03-31") == 12
        assert compute_meses("", "2023-06-30") == 12

    def test_q1_jan_to_mar(self):
        """Jan 1 → Mar 31 = 3 months (Q1, ITR)."""
        assert compute_meses("2023-01-01", "2023-03-31") == 3

    def test_h1_jan_to_jun(self):
        """Jan 1 → Jun 30 = 6 months (H1, ITR)."""
        assert compute_meses("2023-01-01", "2023-06-30") == 6

    def test_9m_jan_to_sep(self):
        """Jan 1 → Sep 30 = 9 months (9M, ITR)."""
        assert compute_meses("2023-01-01", "2023-09-30") == 9

    def test_annual_jan_to_dec(self):
        """Jan 1 → Dec 31 = 12 months (annual, DFP)."""
        assert compute_meses("2023-01-01", "2023-12-31") == 12

    def test_15_month_transition(self):
        """Jan 1 2023 → Mar 31 2024 = 15 months (transition period).

        The OLD implementation bucketed this to 12 — losing the signal.
        rapinav2 preserves 15.
        """
        assert compute_meses("2023-01-01", "2024-03-31") == 15

    def test_non_calendar_fy_jul_to_jun(self):
        """Jul 1 2023 → Jun 30 2024 = 12 months (non-calendar fiscal year)."""
        assert compute_meses("2023-07-01", "2024-06-30") == 12

    def test_non_calendar_fy_oct_to_mar(self):
        """Oct 1 2023 → Mar 31 2024 = 6 months (non-calendar FY H1)."""
        assert compute_meses("2023-10-01", "2024-03-31") == 6

    def test_non_calendar_fy_apr_to_mar(self):
        """Apr 1 2018 → Mar 31 2019 = 12 months (Apr→Mar fiscal year)."""
        assert compute_meses("2018-04-01", "2019-03-31") == 12

    def test_whitespace_dt_ini_treated_as_snapshot(self):
        """Whitespace-only DT_INI_EXERC → treated as empty → meses=12."""
        assert compute_meses("   ", "2023-12-31") == 12

    def test_invalid_dates_return_zero(self):
        """Invalid date strings → return 0 (caller should drop)."""
        assert compute_meses("not-a-date", "2023-12-31") == 0
        assert compute_meses("2023-01-01", "not-a-date") == 0
        assert compute_meses("2023-13-01", "2023-12-31") == 0  # invalid month

    def test_inclusive_formula_not_off_by_one(self):
        """Verify the +1 inclusive formula: Jan→Mar = 3, not 2.

        The OLD implementation used (fim.month - ini.month) = 2 for Jan→Mar,
        which happened to bucket to 3 via rounding but was wrong.
        """
        # Jan 1 → Jan 31 = 1 month → but this would be meses=1 (invalid, dropped)
        assert compute_meses("2023-01-01", "2023-01-31") == 1
        # Feb 1 → Mar 31 = 2 months
        assert compute_meses("2023-02-01", "2023-03-31") == 2
        # Jan 1 → Mar 31 = 3 months (inclusive)
        assert compute_meses("2023-01-01", "2023-03-31") == 3


# ===========================================================================
# is_snapshot / is_flow
# ===========================================================================


class TestSnapshotVsFlow:
    """Test snapshot vs flow detection."""

    def test_empty_dt_ini_is_snapshot(self):
        assert is_snapshot("") is True
        assert is_snapshot("   ") is True

    def test_non_empty_dt_ini_is_flow(self):
        assert is_flow("2023-01-01") is True
        assert is_flow("2023-07-01") is True

    def test_empty_dt_ini_is_not_flow(self):
        assert is_flow("") is False

    def test_non_empty_dt_ini_is_not_snapshot(self):
        assert is_snapshot("2023-01-01") is False


# ===========================================================================
# should_keep_row — ORDEM_EXERC filter
# ===========================================================================


class TestShouldKeepRow:
    """Test ORDEM_EXERC filtering (rapinav2's dedup logic)."""

    def test_ultimo_always_kept(self):
        assert should_keep_row("ÚLTIMO", "2023-12-31") is True
        assert should_keep_row("ULTIMO", "2023-12-31") is True

    def test_penultimo_2009_kept(self):
        """PENÚLTIMO for 2009 is kept (2009 backfill trick)."""
        assert should_keep_row("PENÚLTIMO", "2009-12-31") is True
        assert should_keep_row("PENULTIMO", "2009-12-31") is True

    def test_penultimo_non_2009_dropped(self):
        """PENÚLTIMO for any year other than 2009 is dropped (comparative duplicate)."""
        assert should_keep_row("PENÚLTIMO", "2023-12-31") is False
        assert should_keep_row("PENÚLTIMO", "2010-12-31") is False
        assert should_keep_row("PENULTIMO", "2015-06-30") is False

    def test_unknown_ordem_dropped(self):
        assert should_keep_row("UNKNOWN", "2023-12-31") is False

    def test_empty_ordem_kept(self):
        """Defensive: keep if ordem_exerc is unknown/empty."""
        assert should_keep_row("", "2023-12-31") is True


# ===========================================================================
# is_valid_meses
# ===========================================================================


class TestIsValidMeses:
    """Test meses validity check (rapinav2 drops meses % 3 != 0)."""

    def test_valid_multiples_of_3(self):
        assert is_valid_meses(3) is True
        assert is_valid_meses(6) is True
        assert is_valid_meses(9) is True
        assert is_valid_meses(12) is True
        assert is_valid_meses(15) is True

    def test_invalid_non_multiples(self):
        assert is_valid_meses(0) is False
        assert is_valid_meses(1) is False
        assert is_valid_meses(2) is False
        assert is_valid_meses(4) is False
        assert is_valid_meses(7) is False
        assert is_valid_meses(11) is False
        assert is_valid_meses(13) is False
        assert is_valid_meses(14) is False

    def test_negative_invalid(self):
        assert is_valid_meses(-3) is False
