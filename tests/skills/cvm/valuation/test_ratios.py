"""tests/skills/cvm/valuation/test_ratios.py -- Tests for the ratios() mode.

[Phase 2C] Split out of the monolithic test_valuation.py. Uses the shared
valuation_env fixture (conftest.py) which mocks calculations engines +
metrics + _get_price.
"""
from __future__ import annotations


class TestRatiosMode:
    """Tests for skills.cvm.valuation.valuation.ratios()."""

    def test_ratios_ok(self, valuation_env):
        """ratios() returns status=ok with all expected ratio keys populated."""
        from skills.cvm.valuation.valuation import ratios
        result = ratios(company="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"

        r = result["ratios"]
        # Price (mocked)
        assert r["price"] == 38.50
        # Shares (mocked at 13e9)
        assert r["total_shares"] == 13_000_000_000
        # Market Cap = 38.5 * 13e9 = 500.5e9
        assert r["market_cap"] is not None
        assert r["market_cap"] == 38.5 * 13e9  # 500,500,000,000

        # EPS = 120e9 / 13e9 ≈ 9.23
        assert r["eps"] is not None
        assert 9.0 < r["eps"] < 10.0

        # P/L = market_cap / lucro_liquido = 500.5e9 / 120e9 ≈ 4.17
        assert r["p_l"] is not None
        assert 3.5 < r["p_l"] < 4.5

        # VPA = 350e9 / 13e9 ≈ 26.92
        assert r["vpa"] is not None
        assert 26.0 < r["vpa"] < 28.0

        # P/VPA = 500.5e9 / 350e9 ≈ 1.43
        assert r["p_vpa"] is not None
        assert 1.3 < r["p_vpa"] < 1.5

        # EV = Market Cap + (Debt - Cash) = 500.5e9 + (100e9 - 30e9) = 570.5e9
        assert r["ev"] is not None
        assert r["ev"] == 570_500_000_000

        # P/EBIT = market_cap / ebit = 500.5e9 / 70e9 ≈ 7.15
        assert r["p_ebit"] is not None

        # EBITDA = ebit + da = 70e9 + 15e9 = 85e9
        assert r["ebitda"] == 85_000_000_000
        assert r["ebitda_method"] == "ebit+da"

        # EV/EBITDA = 570.5e9 / 85e9 ≈ 6.71
        assert r["ev_ebitda"] is not None
        assert 6.0 < r["ev_ebitda"] < 7.0

        # PSR = market_cap / receita = 500.5e9 / 280e9 ≈ 1.79
        assert r["psr"] is not None
        assert 1.5 < r["psr"] < 2.0

        # FCF = FCO + FCI = 80e9 + (-30e9) = 50e9
        assert r["fcf"] == 50_000_000_000
        # P/FCF = 500.5e9 / 50e9 ≈ 10.01
        assert r["p_fcf"] is not None
        assert 9.0 < r["p_fcf"] < 11.0

        # DPA (mocked at 1.85)
        assert r["dpa"] == 1.85
        # Dividend Yield = 1.85 / 38.5 ≈ 0.0481 (~4.8%)
        assert r["dividend_yield"] is not None
        assert 0.03 < r["dividend_yield"] < 0.06

        # Divida Líquida / EBITDA = (100e9 - 30e9) / 85e9 ≈ 0.82
        assert r["divida_liquida_ebitda"] is not None
        assert 0.7 < r["divida_liquida_ebitda"] < 0.9

        # [Phase 2B] Mocked calculations metrics (fundamental ratios)
        assert r["roic"] == 0.18
        assert r["graham_number"] == 75.0
        assert r["roe"] == 0.28
        assert r["roa"] == 0.15
        assert r["margem_bruta"] == 0.35
        assert r["margem_operacional"] == 0.25
        assert r["margem_liquida"] == 0.20
        assert r["divida_pl"] == 0.29
        assert r["giro_ativos"] == 0.35
        assert r["liquidez_corrente"] == 1.5

        # price_source present
        assert r["price_source"] is not None

    def test_ratios_no_company(self, valuation_env):
        """ratios() with no company returns status=error."""
        from skills.cvm.valuation.valuation import ratios
        result = ratios()
        assert result["status"] == "error"

    def test_ratios_invalid_ticker(self, valuation_env):
        """ratios() with invalid ticker returns status=error."""
        from skills.cvm.valuation.valuation import ratios
        result = ratios(company="!!!")
        assert result["status"] == "error"

    def test_ratios_missing_price(self, valuation_env, monkeypatch):
        """If _get_price returns no usable price, ratios() returns
        outer status=ok but ratios.status=error with 'Price unavailable'."""
        # Override the fixture's price mock to simulate a price-source failure.
        def mock_get_price_fail(ticker):
            return {"status": "error", "source": "all_failed",
                    "error": "all price sources unavailable"}
        monkeypatch.setattr(
            "skills.cvm.valuation.valuation._get_price", mock_get_price_fail)

        from skills.cvm.valuation.valuation import ratios
        result = ratios(company="PETR4")
        assert result["status"] == "ok"  # outer status ok
        assert result["ratios"]["status"] == "error"
        assert "Price unavailable" in result["ratios"]["error"]
