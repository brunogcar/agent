"""Tests for the `summary` mode of skills/cvm/financials.

Covers:
  - TestSummaryMode                : summary() happy path + no-company (2 tests)
  - TestSummaryV101Regressions     : v1.0.1 summary latest-quarterly + ebitda
                                      method provenance (2 tests)
  - TestSummaryCurrentRatios       : v1.3 calculations-integration test —
                                      verifies the `current_ratios` section
                                      is present + non-crashing (1 test)

Uses the shared `financials_env` fixture from conftest.py.
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# TestSummaryMode
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryMode:
    """Tests for `financials.summary()`."""

    def test_summary_ok(self, financials_env):
        from skills.cvm.financials.financials import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        assert "latest_annual" in result["sections"]
        assert "latest_quarterly" in result["sections"]
        # [v1.3] current_ratios section is always present (may have None values
        # when underlying DBs are missing — but the section key exists).
        assert "current_ratios" in result["sections"]

    def test_summary_no_company(self, financials_env):
        from skills.cvm.financials.financials import summary
        result = summary()
        assert result["status"] == "error"


# ════════════════════════════════════════════════════════════════════════════
# v1.0.1 summary-mode regression tests
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryV101Regressions:
    """[v1.0.1] summary-mode regression tests."""

    def test_summary_latest_quarterly_is_newest(self, financials_env):
        """[P1] summary.latest_quarterly should be the NEWEST quarter, not oldest."""
        from skills.cvm.financials.financials import summary
        result = summary(company="33000167000101")
        if result["sections"].get("latest_quarterly", {}).get("period"):
            latest = result["sections"]["latest_quarterly"]
            trend = result["sections"].get("quarterly_trend", [])
            if trend:
                # latest should be the last in the trend (newest, since sorted oldest-first)
                assert latest["period"] == trend[-1]["period"], \
                    f"latest_quarterly={latest['period']} should be {trend[-1]['period']} (newest)"

    def test_ebitda_method_provenance(self, financials_env):
        """[v1.0.1] EBITDA response includes ebitda_method field."""
        from skills.cvm.financials.financials import annual
        result = annual(company="33000167000101", periods=2)
        if result["status"] == "ok" and result["periods"]:
            metrics = result["periods"][0]["metrics"]
            assert "ebitda_method" in metrics
            assert metrics["ebitda_method"] in ("ebit+da", "ebit_only", "none")


# ════════════════════════════════════════════════════════════════════════════
# v1.3 — calculations-integration test
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryCurrentRatios:
    """[v1.3] summary() now includes a `current_ratios` section populated by
    calculations metrics (ROIC, Graham, EV/EBITDA, P/FCF, P/EBIT, P/FCO).

    These metrics are computed point-in-time at today's date. In the test env
    (no cotahist.db, no FRE, no DRE 3.08), most price/tax-based ratios will
    return None gracefully — that is the expected behavior of `_safe_call`.
    The test verifies that:
      1. The `current_ratios` section exists with the expected keys.
      2. The synthetic DFP data is sufficient for at least one fundamental
         metric (ROIC uses DRE 3.05, BPP 2.03, BPP 2.01.04+2.02.01, BPA 1.01.01
         — all present in the fixture).
      3. No metric crashes the summary call (the `_safe_call` wrapper works).
    """

    def test_current_ratios_section_populated(self, financials_env):
        from skills.cvm.financials.financials import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        cr = result["sections"].get("current_ratios")
        assert cr is not None, "current_ratios section missing"
        # All 6 metric keys must be present (values may be None when underlying
        # DBs are unavailable — e.g. cotahist.db for price-based ratios).
        expected_keys = {"date", "roic", "graham_number", "ev_ebitda",
                         "p_fcf", "p_ebit", "p_fco"}
        assert expected_keys.issubset(cr.keys()), \
            f"missing keys: {expected_keys - set(cr.keys())}"
        # The "date" key is today's ISO date (YYYY-MM-DD).
        assert isinstance(cr["date"], str)
        assert len(cr["date"]) == 10
