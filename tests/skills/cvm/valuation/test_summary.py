"""tests/skills/cvm/valuation/test_summary.py -- Tests for the summary() mode.

[Phase 2C] Split out of the monolithic test_valuation.py. Uses the shared
valuation_env fixture (conftest.py) which mocks calculations engines +
metrics + _get_price.
"""
from __future__ import annotations


class TestSummaryMode:
    """Tests for skills.cvm.valuation.valuation.summary()."""

    def test_summary_ok(self, valuation_env):
        """summary() returns status=ok with ratios + data_availability."""
        from skills.cvm.valuation.valuation import summary
        result = summary(company="PETR4")
        assert result["status"] == "ok"
        assert "ratios" in result
        assert "data_availability" in result
        # All mocked sources resolve to "ok"
        assert result["data_availability"]["price"] == "ok"
        assert result["data_availability"]["dfp_ttm"] == "ok"
        assert result["data_availability"]["fre_shares"] == "ok"

        # [v1.4-valuation] headline_v13_metrics block surfaces the 10 most
        # important new v1.3 metrics at the top level (mirrored from ratios).
        headline = result["headline_v13_metrics"]
        assert headline["ev_sales"] == 2.05
        assert headline["ev_fcf"] == 11.41
        assert headline["quick_ratio"] == 1.10
        assert headline["cash_ratio"] == 0.30
        assert headline["ocf_margin"] == 0.286
        assert headline["fcf_margin"] == 0.179
        assert headline["interest_coverage"] == 8.0
        assert headline["cash_flow_to_debt"] == 0.80
        assert headline["sustainable_growth"] == 0.14
        assert headline["p_tangible_book"] == 1.55

    def test_summary_no_company(self, valuation_env):
        """summary() with no company returns status=error (propagated from ratios)."""
        from skills.cvm.valuation.valuation import summary
        result = summary()
        assert result["status"] == "error"
