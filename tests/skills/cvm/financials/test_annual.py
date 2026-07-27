"""Tests for the `annual` mode of skills/cvm/financials.

Covers TestAnnualMode (3 tests):
  - test_annual_ok            : full assertion sweep over metrics + ratios
  - test_annual_no_company    : annual() with no args → status=error
  - test_annual_not_found     : annual(company="NONEXISTENT") → status=not_found

Uses the shared `financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestAnnualMode:
    """Tests for `financials.annual()`."""

    def test_annual_ok(self, financials_env):
        from skills.cvm.financials.financials import annual
        result = annual(company="33000167000101", periods=5)
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert len(result["periods"]) == 2  # 2023 + 2022
        # Latest first
        assert result["periods"][0]["period"] == "2023"
        metrics = result["periods"][0]["metrics"]
        # valor=100000000, escala="MIL" → 100 billion
        assert metrics["ativo_total"] == 100000000000.0
        assert metrics["receita_liquida"] == 50000000000.0
        # EBITDA = EBIT (20B) + D&A (3B) = 23B
        assert metrics["ebitda"] == 23000000000.0
        ratios = result["periods"][0]["ratios"]
        assert ratios["marg_bruta"] == 0.6
        assert ratios["roe"] == 0.3

    def test_annual_no_company(self, financials_env):
        from skills.cvm.financials.financials import annual
        result = annual()
        assert result["status"] == "error"

    def test_annual_not_found(self, financials_env):
        from skills.cvm.financials.financials import annual
        result = annual(company="NONEXISTENT")
        assert result["status"] == "not_found"
