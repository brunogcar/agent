"""tests/skills/cvm/valuation/test_ratios.py -- Tests for the ratios() mode.

[Phase 2C] Split out of the monolithic test_valuation.py. Uses the shared
valuation_env fixture (conftest.py) which mocks calculations engines +
compute_all_ratios + _get_price.

[v1.5] Updated for the compute_all_ratios refactor:
  - Phase 2B metrics now use English registry keys (gross_margin instead of
    margem_bruta, debt_equity instead of divida_pl, etc.).
  - p_tangible_book renamed to price_to_tangible_book.
  - `vpa` is now P/VPA (registry price ratio), not per-share VPA.
  - `dpa` is now Div Yield (registry price ratio), not per-share DPA.
  - Manual computations of p_l, p_vpa, ev, psr, dividend_yield, market_cap,
    divida_liquida_ebitda are preserved.
"""
from __future__ import annotations


class TestRatiosMode:
    """Tests for skills.cvm.valuation.modes.ratios.ratios()."""

    def test_ratios_ok(self, valuation_env):
        """ratios() returns status=ok with all expected ratio keys populated."""
        from skills.cvm.valuation.modes.ratios import ratios
        result = ratios(company="PETR4")
        assert result["status"] == "ok"
        assert result["ticker"] == "PETR4"

        r = result["ratios"]
        # Price (mocked)
        assert r["price"] == 38.50
        # Shares (mocked at 13e9)
        assert r["total_shares"] == 13_000_000_000
        # Market Cap = 38.5 * 13e9 = 500.5e9 (manual computation, kept)
        assert r["market_cap"] is not None
        assert r["market_cap"] == 38.5 * 13e9  # 500,500,000,000

        # EPS = 120e9 / 13e9 ≈ 9.23 (manual computation; key "eps" preserved
        # because registry uses key "lpa" for P/L — no conflict)
        assert r["eps"] is not None
        assert 9.0 < r["eps"] < 10.0

        # P/L = market_cap / lucro_liquido = 500.5e9 / 120e9 ≈ 4.17
        # (manual computation, key "p_l" preserved; registry uses "lpa" for P/L)
        assert r["p_l"] is not None
        assert 3.5 < r["p_l"] < 4.5

        # [v1.5] vpa is per-share VPA (PL / shares = 350e9 / 13e9 ≈ 26.92).
        # compute_all_ratios returns P/VPA under the "pvpa" key (registry
        # ratio_key), but the manual per-share VPA is restored to "vpa".
        assert r["vpa"] is not None
        assert 25.0 < r["vpa"] < 28.0  # per-share VPA ≈ 26.92

        # P/VPA = 500.5e9 / 350e9 ≈ 1.43 (manual computation, key "p_vpa")
        assert r["p_vpa"] is not None
        assert 1.3 < r["p_vpa"] < 1.5

        # EV = Market Cap + (Debt - Cash) = 500.5e9 + (100e9 - 30e9) = 570.5e9
        # (manual computation, key "ev" preserved — registry has no "ev" key)
        assert r["ev"] is not None
        assert r["ev"] == 570_500_000_000

        # P/EBIT (registry overrides manual computation)
        # Manual: market_cap / ebit = 500.5e9 / 70e9 ≈ 7.15
        # Registry mock returns 7.15 (matching)
        assert r["p_ebit"] is not None
        assert 6.0 < r["p_ebit"] < 8.0

        # EBITDA = ebit + da = 70e9 + 15e9 = 85e9 (manual, key "ebitda")
        assert r["ebitda"] == 85_000_000_000
        assert r["ebitda_method"] == "ebit+da"

        # EV/EBITDA (registry overrides manual computation)
        # Manual: 570.5e9 / 85e9 ≈ 6.71
        # Registry mock returns 6.71 (matching)
        assert r["ev_ebitda"] is not None
        assert 6.0 < r["ev_ebitda"] < 7.0

        # PSR = market_cap / receita = 500.5e9 / 280e9 ≈ 1.79
        # (manual computation, key "psr" preserved; registry uses "rps")
        assert r["psr"] is not None
        assert 1.5 < r["psr"] < 2.0

        # FCF = FCO + FCI = 80e9 + (-30e9) = 50e9 (manual, key "fcf")
        assert r["fcf"] == 50_000_000_000
        # P/FCF (registry overrides manual computation)
        # Manual: 500.5e9 / 50e9 ≈ 10.01
        # Registry mock returns 10.01 (matching)
        assert r["p_fcf"] is not None
        assert 9.0 < r["p_fcf"] < 11.0

        # [v1.5] dpa is per-share DPA (1.85 R$/share, from dividends_at engine).
        # compute_all_ratios returns Div Yield under the "dy" key (registry
        # ratio_key), but the manual per-share DPA is restored to "dpa".
        assert r["dpa"] is not None
        assert 1.5 < r["dpa"] < 2.0  # per-share DPA = 1.85

        # Dividend Yield (manual computation, key "dividend_yield" preserved)
        # = dpa_ttm / price = 1.85 / 38.5 ≈ 0.0481 (~4.8%)
        assert r["dividend_yield"] is not None
        assert 0.03 < r["dividend_yield"] < 0.06

        # Divida Líquida / EBITDA = (100e9 - 30e9) / 85e9 ≈ 0.82
        # (manual computation, key "divida_liquida_ebitda" preserved;
        # registry uses "net_debt_ebitda" — different key, both present)
        assert r["divida_liquida_ebitda"] is not None
        assert 0.7 < r["divida_liquida_ebitda"] < 0.9

        # [v1.5] Calculations-backed metrics via compute_all_ratios()
        # (mocked in conftest). Values come from the mock dict.
        assert r["roic"] == 0.18
        assert r["graham_number"] == 75.0
        assert r["roe"] == 0.28
        assert r["roa"] == 0.15
        # Phase 2B metrics -- English registry keys (was Portuguese in v2.0.0)
        assert r["gross_margin"] == 0.35
        assert r["operating_margin"] == 0.25
        assert r["net_margin"] == 0.20
        assert r["debt_equity"] == 0.29
        assert r["asset_turnover"] == 0.35
        assert r["current_ratio"] == 1.5

        # [v1.4-valuation] 15 NEW v1.3 metrics (mocked in conftest)
        assert r["ev_sales"] == 2.05
        assert r["ev_fcf"] == 11.41
        assert r["cash_ratio"] == 0.30
        assert r["quick_ratio"] == 1.10
        assert r["ocf_margin"] == 0.286
        assert r["fcf_margin"] == 0.179
        assert r["working_capital"] == 50e9
        assert r["cash_flow_to_debt"] == 0.80
        assert r["retention_ratio"] == 0.50
        assert r["sustainable_growth"] == 0.14
        assert r["interest_coverage"] == 8.0
        assert r["inventory_turnover"] == 5.0
        assert r["receivables_turnover"] == 8.0
        assert r["fixed_asset_turnover"] == 0.80
        # Renamed from p_tangible_book (v2.0.0) to price_to_tangible_book (registry)
        assert r["price_to_tangible_book"] == 1.55

        # Additional metrics that the registry surfaces automatically (v1.5)
        # These come from the mock and verify that ALL 37 metrics are present.
        assert "ebitda_margin" in r
        assert "net_debt_ebitda" in r
        assert "capex_revenue" in r
        assert "effective_tax_rate" in r
        # Per-share metrics (registry returns price ratios, not per-share values)
        assert "lpa" in r   # P/L value
        assert "rps" in r   # PSR value

        # price_source present
        assert r["price_source"] is not None

    def test_ratios_no_company(self, valuation_env):
        """ratios() with no company returns status=error."""
        from skills.cvm.valuation.modes.ratios import ratios
        result = ratios()
        assert result["status"] == "error"

    def test_ratios_invalid_ticker(self, valuation_env):
        """ratios() with invalid ticker returns status=error."""
        from skills.cvm.valuation.modes.ratios import ratios
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
            "skills.cvm.valuation.modes.ratios._get_price", mock_get_price_fail)

        from skills.cvm.valuation.modes.ratios import ratios
        result = ratios(company="PETR4")
        assert result["status"] == "ok"  # outer status ok
        assert result["ratios"]["status"] == "error"
        assert "Price unavailable" in result["ratios"]["error"]

    def test_ratios_uses_compute_all_ratios(self, valuation_env, monkeypatch):
        """[v1.5] ratios() must call compute_all_ratios and merge its output."""
        # Track calls to compute_all_ratios
        call_log: list = []

        def tracking_mock(company, date, categories=None, exclude=None):
            call_log.append({
                "company": company, "date": date,
                "categories": categories, "exclude": exclude,
            })
            # Return a single sentinel metric to verify it lands in ratios
            return {"_sentinel_metric": 42.0}

        monkeypatch.setattr(
            "skills.cvm.valuation.modes.ratios.compute_all_ratios",
            tracking_mock)

        from skills.cvm.valuation.modes.ratios import ratios
        result = ratios(company="PETR4")
        assert result["status"] == "ok"
        # Confirm compute_all_ratios was called once with (ticker, today)
        assert len(call_log) == 1
        assert call_log[0]["company"] == "PETR4"
        # No category filter — valuation wants all 37 metrics
        assert call_log[0]["categories"] is None
        assert call_log[0]["exclude"] is None
        # The sentinel metric from the mock should be present in ratios
        assert result["ratios"]["_sentinel_metric"] == 42.0
