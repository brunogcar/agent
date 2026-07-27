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

    def test_summary_no_company(self, valuation_env):
        """summary() with no company returns status=error (propagated from ratios)."""
        from skills.cvm.valuation.valuation import summary
        result = summary()
        assert result["status"] == "error"
