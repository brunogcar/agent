"""TTM derivation regression test — verifies TTM self-consistency against real CVM data.

This test verifies that the TTM derivation algorithm (DFP_prior - ITR_prior_same_period
+ ITR_current) produces correct results by checking data-existence and structural
properties against real CVM databases. It does NOT assume profitability — companies
can have negative EBIT/earnings during downturns (e.g., PETR4 during the 2015 oil crash).

Test design:
- **3-company tests** (PETR4, KLBN11, SUZB3): verify engines return data (not None)
  across multiple companies — catches company-specific data gaps.
- **1-company tests** (PETR4 only): verify structural properties (date ordering,
  no duplicates, periods non-empty) — these are engine properties, not company-specific.
- **Reasonableness tests** (PETR4 only): verify EBIT < revenue and earnings < EBIT
  ONLY when both values are positive (losses can break these relationships).

Marked @pytest.mark.slow because it requires real CVM databases (DFP + ITR).
Run with: python -m pytest -m slow -v
"""
import pytest
from skills.cvm.calculations.engines.dre.revenue import revenue_at, revenue_periods
from skills.cvm.calculations.engines.dre.ebit import ebit_at, ebit_periods
from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at, ttm_earnings_periods
from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at


pytestmark = pytest.mark.slow


# ════════════════════════════════════════════════════════════════════════════
# 3-company tests: verify engines return data (not None) across companies
# ════════════════════════════════════════════════════════════════════════════

class TestTTMDataExists:
    """Verify TTM engines return data (not None) for multiple companies."""

    @pytest.mark.parametrize("ticker", ["PETR4", "KLBN11", "SUZB3"])
    def test_ttm_revenue_not_none(self, ticker):
        """TTM revenue should be computable (not None) for listed companies."""
        result = revenue_at(ticker, "2024-06-30")
        assert result is not None, f"{ticker}: TTM revenue is None (no data?)"

    @pytest.mark.parametrize("ticker", ["PETR4", "KLBN11", "SUZB3"])
    def test_ttm_ebit_not_none(self, ticker):
        """TTM EBIT should be computable (not None). Can be negative (losses)."""
        result = ebit_at(ticker, "2024-06-30")
        assert result is not None, f"{ticker}: TTM EBIT is None (no data?)"

    @pytest.mark.parametrize("ticker", ["PETR4", "KLBN11", "SUZB3"])
    def test_ttm_earnings_not_none(self, ticker):
        """TTM earnings should be computable (not None). Can be negative (losses)."""
        result = ttm_earnings_at(ticker, "2024-06-30")
        assert result is not None, f"{ticker}: TTM earnings is None (no data?)"

    @pytest.mark.parametrize("ticker", ["PETR4", "KLBN11", "SUZB3"])
    def test_operating_cf_not_none(self, ticker):
        """TTM FCO should be computable (not None). Can be negative (cash-burning)."""
        result = operating_cf_at(ticker, "2024-06-30")
        assert result is not None, f"{ticker}: TTM FCO is None"

    @pytest.mark.parametrize("ticker", ["PETR4", "KLBN11", "SUZB3"])
    def test_investing_cf_not_none(self, ticker):
        """TTM FCI should be computable (not None). Typically negative (outflow)."""
        result = investing_cf_at(ticker, "2024-06-30")
        assert result is not None, f"{ticker}: TTM FCI is None"


# ════════════════════════════════════════════════════════════════════════════
# 1-company structural tests: verify engine properties (not company-specific)
# ════════════════════════════════════════════════════════════════════════════

class TestTTMStructure:
    """Verify TTM periods have correct structural properties (PETR4 only)."""

    def test_revenue_periods_nonempty(self):
        """revenue_periods should return a non-empty list."""
        periods = revenue_periods("PETR4")
        assert len(periods) >= 4, f"Expected >= 4 revenue periods, got {len(periods)}"

    def test_ebit_periods_nonempty(self):
        """ebit_periods should return a non-empty list."""
        periods = ebit_periods("PETR4")
        assert len(periods) >= 4, f"Expected >= 4 EBIT periods, got {len(periods)}"

    def test_revenue_periods_have_correct_keys(self):
        """Each revenue period should have 'date' and 'ttm_rev' keys."""
        periods = revenue_periods("PETR4")
        for p in periods:
            assert "date" in p, f"Missing 'date' key: {p}"
            assert "ttm_rev" in p, f"Missing 'ttm_rev' key: {p}"
            assert p["ttm_rev"] is not None, f"ttm_rev is None at {p.get('date')}"

    def test_ebit_periods_have_correct_keys(self):
        """Each EBIT period should have 'date' and 'ttm_ebit' keys."""
        periods = ebit_periods("PETR4")
        for p in periods:
            assert "date" in p, f"Missing 'date' key: {p}"
            assert "ttm_ebit" in p, f"Missing 'ttm_ebit' key: {p}"
            assert p["ttm_ebit"] is not None, f"ttm_ebit is None at {p.get('date')}"

    def test_revenue_periods_sorted_oldest_first(self):
        """revenue_periods should return dates sorted oldest-first."""
        periods = revenue_periods("PETR4")
        dates = [p["date"] for p in periods]
        assert dates == sorted(dates), "Revenue periods should be sorted oldest-first"

    def test_ebit_periods_sorted_oldest_first(self):
        """ebit_periods should return dates sorted oldest-first."""
        periods = ebit_periods("PETR4")
        dates = [p["date"] for p in periods]
        assert dates == sorted(dates), "EBIT periods should be sorted oldest-first"

    def test_revenue_periods_no_duplicate_dates(self):
        """revenue_periods should not have duplicate dates."""
        periods = revenue_periods("PETR4")
        dates = [p["date"] for p in periods]
        assert len(dates) == len(set(dates)), "Revenue periods should not have duplicate dates"

    def test_ebit_periods_no_duplicate_dates(self):
        """ebit_periods should not have duplicate dates."""
        periods = ebit_periods("PETR4")
        dates = [p["date"] for p in periods]
        assert len(dates) == len(set(dates)), "EBIT periods should not have duplicate dates"


# ════════════════════════════════════════════════════════════════════════════
# 1-company reasonableness tests: only check when both values are positive
# ════════════════════════════════════════════════════════════════════════════

class TestTTMReasonableness:
    """Verify TTM relationships hold when values are positive (PETR4 only).

    These tests only assert when BOTH values are positive — companies can have
    negative EBIT/earnings during downturns (e.g., PETR4 in 2015), which would
    break the EBIT < revenue and earnings < EBIT relationships.
    """

    def test_ebit_less_than_revenue_when_profitable(self):
        """When both positive: EBIT < revenue (EBIT is a margin of revenue)."""
        rev = revenue_at("PETR4", "2024-06-30")
        ebit = ebit_at("PETR4", "2024-06-30")
        assert rev is not None and ebit is not None
        # Only check when both are positive (losses can break this)
        if rev > 0 and ebit > 0:
            assert ebit < rev, f"EBIT ({ebit}) should be < revenue ({rev}) when both positive"

    def test_earnings_less_than_ebit_when_profitable(self):
        """When both positive: earnings < EBIT (earnings = EBIT - tax - financial expenses)."""
        ebit = ebit_at("PETR4", "2024-06-30")
        earnings = ttm_earnings_at("PETR4", "2024-06-30")
        assert ebit is not None and earnings is not None
        # Only check when both are positive
        if ebit > 0 and earnings > 0:
            assert earnings < ebit, f"earnings ({earnings}) should be < EBIT ({ebit}) when both positive"
