"""Tests for the `summary` mode of skills/cvm/financials.

Covers:
  - TestSummaryMode                : summary() happy path + no-company (2 tests)
  - TestSummaryV101Regressions     : v1.0.1 summary latest-quarterly + ebitda
                                      method provenance (2 tests)
  - TestSummaryCurrentRatios       : v1.3/v1.5 calculations-integration test —
                                      verifies the `current_ratios` section is
                                      populated by compute_all_ratios() (1 test)

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
# v1.5 — compute_all_ratios integration test
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryCurrentRatios:
    """[v1.5] summary() now populates `current_ratios` via compute_all_ratios().

    Prior to v1.5, this section had 6 hardcoded metric imports (ROIC, Graham,
    EV/EBITDA, P/FCF, P/EBIT, P/FCO — all in the valuation category). The v1.5
    refactor replaces the hardcoded block with a single call to
    ``compute_all_ratios(company, today, categories=[...], exclude=[...])``.

    The new categories filter selects the profitability / liquidity / leverage
    / efficiency / growth / tax buckets — currently 25 metrics, all of which
    should appear in `current_ratios` regardless of whether their underlying
    DBs are available. Per-share metrics (lpa, vpa, dpa, rps) are explicitly
    excluded because they belong in the valuation skill.

    This test verifies that:
      1. The `current_ratios` section exists with a `date` key.
      2. The section contains the expected metric NAMES (not just the old
         6 keys). New metrics added to the registry auto-appear here.
      3. No metric crashes the summary call (compute_all_ratios catches
         per-metric exceptions and stores None).
      4. The synthetic DFP data is sufficient for at least one fundamental
         metric (e.g., ROE uses DRE 3.11 + BPP 2.03 — both present in the
         fixture).
    """

    def test_current_ratios_section_populated(self, financials_env):
        from skills.cvm.financials.financials import summary
        result = summary(company="33000167000101")
        assert result["status"] == "ok"
        cr = result["sections"].get("current_ratios")
        assert cr is not None, "current_ratios section missing"
        # The "date" key is today's ISO date (YYYY-MM-DD).
        assert isinstance(cr.get("date"), str)
        assert len(cr["date"]) == 10
        # Spot-check a few metric names that MUST be present after the v1.5
        # refactor — these come from the profitability / liquidity / leverage
        # / efficiency / growth / tax categories.
        for metric_name in ("roe", "roa", "roic", "current_ratio",
                            "debt_equity", "asset_turnover",
                            "effective_tax_rate", "sustainable_growth"):
            assert metric_name in cr, \
                f"current_ratios missing metric '{metric_name}' (got {sorted(cr.keys())})"
        # Per-share metrics MUST be excluded (they belong in valuation).
        for excluded in ("lpa", "vpa", "dpa", "rps"):
            assert excluded not in cr, \
                f"per-share metric '{excluded}' should be excluded from current_ratios"
        # Valuation-category metrics MUST also be absent now (the v1.3
        # hardcoded list — ev_ebitda, graham_number, p_ebit, p_fcf, p_fco —
        # is no longer surfaced here; it lives in valuation.ratios()).
        for valuation_metric in ("ev_ebitda", "graham_number",
                                 "p_ebit", "p_fcf", "p_fco"):
            assert valuation_metric not in cr, \
                f"valuation metric '{valuation_metric}' should not be in current_ratios"
        # Sanity: at least 20 metric keys (we expect ~25). Asserting a floor
        # rather than an exact count so newly-registered metrics don't break
        # the test.
        metric_keys = [k for k in cr if k != "date" and k != "error"]
        assert len(metric_keys) >= 20, \
            f"expected >= 20 metric keys, got {len(metric_keys)}: {sorted(metric_keys)}"
        # At least one fundamental ratio should resolve to a non-None value
        # given the synthetic DFP data (ROE = lucro_liquido / PL; the fixture
        # has both DRE 3.11 = 12M and BPP 2.03 = 40M, so ROE > 0).
        # Note: in the test env cotahist.db is missing, so price-based
        # metrics return None — that's expected. We only require ONE non-None.
        non_none = [k for k in metric_keys if cr[k] is not None]
        assert non_none, \
            f"expected at least one non-None ratio, all are None: {sorted(metric_keys)}"
