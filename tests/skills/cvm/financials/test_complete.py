"""Tests for the `complete` mode of skills/cvm/financials.

Covers TestCompleteMode (5 tests):
  - test_complete_annual_ok        : full DRE statements, annual
  - test_complete_quarterly_ok     : full BPA statements, quarterly
  - test_complete_no_grupo_all_codes: empty grupo → returns all key codes
  - test_complete_unknown_grupo    : unknown grupo name → status=error
  - test_complete_no_company       : no company arg → status=error

Uses the shared `financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestCompleteMode:
    """Tests for `financials.complete()`."""

    def test_complete_annual_ok(self, financials_env):
        from skills.cvm.financials.modes.complete import complete
        result = complete(company="33000167000101", period="annual", grupo="DRE")
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert result["grupo_filter"] == "DRE"
        # Should have DRE key codes
        codes_found = {a["codigo"] for p in result["periods"] for a in p["accounts"]}
        assert "3.01" in codes_found  # Receita Líquida

    def test_complete_quarterly_ok(self, financials_env):
        from skills.cvm.financials.modes.complete import complete
        result = complete(company="33000167000101", period="quarterly", grupo="BPA")
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"

    def test_complete_no_grupo_all_codes(self, financials_env):
        from skills.cvm.financials.modes.complete import complete
        result = complete(company="33000167000101", period="annual")
        assert result["status"] == "ok"
        assert result["grupo_filter"] == "all"

    def test_complete_unknown_grupo(self, financials_env):
        from skills.cvm.financials.modes.complete import complete
        result = complete(company="33000167000101", grupo="INVALID")
        assert result["status"] == "error"

    def test_complete_no_company(self, financials_env):
        from skills.cvm.financials.modes.complete import complete
        result = complete()
        assert result["status"] == "error"
