"""tests/skills/cvm/valuation/test_summary.py -- Tests for the summary() mode.

[Phase 2C] Split out of the monolithic test_valuation.py. Uses the shared
valuation_env fixture (conftest.py) which mocks calculations engines +
compute_all_ratios + _get_price.

[v1.5] The headline_v13_metrics block has been removed from summary() —
all metrics are now in ratios() directly via compute_all_ratios(), so the
headline block was redundant.
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

        # [v1.5] headline_v13_metrics block has been REMOVED from summary().
        # All metrics are now in ratios() directly via compute_all_ratios().
        assert "headline_v13_metrics" not in result

        # The v1.3 metrics are still accessible via ratios (registry keys)
        ratios_block = result["ratios"]
        assert ratios_block.get("ev_sales") == 2.05
        assert ratios_block.get("ev_fcf") == 11.41
        assert ratios_block.get("quick_ratio") == 1.10
        assert ratios_block.get("cash_ratio") == 0.30
        assert ratios_block.get("ocf_margin") == 0.286
        assert ratios_block.get("fcf_margin") == 0.179
        assert ratios_block.get("interest_coverage") == 8.0
        assert ratios_block.get("cash_flow_to_debt") == 0.80
        assert ratios_block.get("sustainable_growth") == 0.14
        # Renamed from p_tangible_book to price_to_tangible_book (registry key)
        assert ratios_block.get("price_to_tangible_book") == 1.55

    def test_summary_no_company(self, valuation_env):
        """summary() with no company returns status=error (propagated from ratios)."""
        from skills.cvm.valuation.valuation import summary
        result = summary()
        assert result["status"] == "error"
