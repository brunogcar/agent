"""Shared fixtures for the valuation skill tests.

[Phase 2C] Valuation now consumes calculations engines + metrics (Phase 2B
refactor). The old fixture built synthetic DFP/FRE/trades DBs and patched
internal helpers (`_get_shares_investsite`, `_get_financials`) that no longer
exist. The new fixture mocks the engine functions at the names bound inside
`skills.cvm.valuation.valuation` (which imports them via
`from <engine_module> import <fn>` -- the bound names are what the SUT actually
calls, so that is the namespace we must patch).

[v1.5] The 25 individual metric mocks (roe_at, gross_margin_at, etc.) have
been removed — valuation.ratios() now calls `compute_all_ratios()` which
walks the registry internally. We mock `compute_all_ratios` itself to return
all 37 metric values deterministically.

Env vars (PLANNER_MODEL etc.) are set by the parent conftest at
``tests/skills/cvm/conftest.py``.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def valuation_env(monkeypatch):
    """Mock calculations engines + compute_all_ratios + price for valuation.ratios().

    All engine functions are patched at the names bound inside
    ``skills.cvm.valuation.valuation`` (NOT at their source modules), because
    valuation.py imports them via ``from <module> import <fn>``. Patching the
    source module would not affect the local references already bound in
    valuation.valuation's namespace.

    ``compute_all_ratios`` is patched at
    ``skills.cvm.valuation.valuation.compute_all_ratios`` (also imported via
    ``from ... import``).

    Known values (BRL, R$/share as noted):
      price          = 38.50
      shares         = 13e9
      earnings (TTM) = 120e9
      revenue        = 280e9
      ebit           = 70e9
      pl             = 350e9
      debt           = 100e9
      cash           = 30e9
      da             = 15e9
      fco            = 80e9
      fci            = -30e9
      dpa (TTM)      = 1.85 (R$/share)

    Derived (for assertion reference):
      market_cap  = 38.5 * 13e9              = 500.5e9
      eps         = 120e9 / 13e9             ≈ 9.23
      vpa (per-share) = 350e9 / 13e9         ≈ 26.92
      p_l         = 500.5e9 / 120e9          ≈ 4.17
      p_vpa       = 500.5e9 / 350e9          ≈ 1.43
      ebitda      = 70e9 + 15e9              = 85e9
      divida_liq  = 100e9 - 30e9             = 70e9
      ev          = 500.5e9 + 70e9           = 570.5e9
      p_ebit      = 500.5e9 / 70e9           ≈ 7.15
      psr         = 500.5e9 / 280e9          ≈ 1.79
      ev_ebitda   = 570.5e9 / 85e9           ≈ 6.71
      fcf         = 80e9 + (-30e9)           = 50e9
      p_fcf       = 500.5e9 / 50e9           ≈ 10.01
      div_yield   = 1.85 / 38.5              ≈ 0.0481 (~4.8%)
      divida_liq_ebitda = 70e9 / 85e9        ≈ 0.82

    [v1.5] compute_all_ratios mock returns all 37 metrics. Values are
    loosely consistent with the engine mocks (ROE=0.28, ROA=0.15, etc.) so
    the assertion ranges remain plausible; the metrics themselves are NOT
    recomputed from engines because the registry call is mocked (we only
    test the wiring — that compute_all_ratios is invoked + its output
    merged into ratios_result via .update()).

    Note on per_share metric overrides:
      The registry's `vpa` metric's ratio_fn returns P/VPA (price ratio),
      NOT the per-share VPA. So after `ratios_result.update(calc_ratios)`,
      `ratios_result["vpa"]` is OVERRIDDEN from per-share VPA (≈26.92) to
      P/VPA (≈1.43). Similarly `dpa` is overridden from per-share DPA (1.85)
      to Div Yield (≈0.048). The manual computations of `p_vpa` and
      `dividend_yield` are preserved (no key conflict).
    """
    # ── Calculations engines (snapshot/TTM fetchers) ───────────────────────
    # Patch at valuation.valuation namespace -- those are the names the SUT
    # actually invokes. (See module docstring for why source-module patching
    # would not work.)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.ttm_earnings_at", lambda c, d: 120e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.revenue_at", lambda c, d: 280e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.ebit_at", lambda c, d: 70e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.pl_at", lambda c, d: 350e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.debt_at", lambda c, d: 100e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.cash_at", lambda c, d: 30e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.shares_at", lambda c, d: 13e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.da_at", lambda c, d: 15e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.operating_cf_at", lambda c, d: 80e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.investing_cf_at", lambda c, d: -30e9)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.dividends_at", lambda c, d: 1.85)

    # ── [v1.5] compute_all_ratios mock ────────────────────────────────────
    # Returns ALL 37 metrics (no filter — valuation calls compute_all_ratios
    # with no categories/exclude args). Values are deterministic and chosen
    # to match the engine mocks where the manual computation already
    # produces a value (e.g. ev_ebitda ≈ 6.71, p_ebit ≈ 7.15) so that
    # existing test assertions still pass.
    def mock_compute_all_ratios(company, date, categories=None, exclude=None):
        return {
            # profitability (9)
            "roe":              0.28,
            "roa":              0.15,
            "roic":             0.18,
            "gross_margin":     0.35,
            "operating_margin": 0.25,
            "net_margin":       0.20,
            "ebitda_margin":    0.303,
            "ocf_margin":       0.286,
            "fcf_margin":       0.179,
            # liquidity (4)
            "cash_ratio":       0.30,
            "current_ratio":    1.5,
            "quick_ratio":      1.10,
            "working_capital":  50e9,
            # leverage (4)
            "cash_flow_to_debt":   0.80,
            "debt_equity":         0.29,
            "interest_coverage":   8.0,
            "net_debt_ebitda":     0.823,
            # efficiency (5)
            "asset_turnover":        0.35,
            "capex_revenue":         0.05,
            "fixed_asset_turnover":  0.80,
            "inventory_turnover":    5.0,
            "receivables_turnover":  8.0,
            # growth (2)
            "retention_ratio":    0.50,
            "sustainable_growth": 0.14,
            # valuation (8) -- these OVERRIDE the manual computations of
            # ev_ebitda, p_ebit, p_fcf, p_fco, graham_number below.
            "ev_ebitda":             6.71,
            "ev_fcf":                11.41,
            "ev_sales":              2.05,
            "graham_number":         75.0,
            "p_ebit":                7.15,
            "p_fcf":                 10.01,
            "p_fco":                 6.26,
            "price_to_tangible_book": 1.55,
            # per_share (4) -- registry returns the price RATIO, not the
            # per-share value. vpa -> P/VPA, dpa -> Div Yield, lpa -> P/L,
            # rps -> PSR. These OVERRIDE the manual per-share vpa + dpa.
            "lpa": 4.17,
            "vpa": 1.43,
            "dpa": 0.048,
            "rps": 1.79,
            # tax (1)
            "effective_tax_rate": 0.34,
        }
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.compute_all_ratios",
        mock_compute_all_ratios)

    # ── Price (kept in valuation.valuation._get_price -- not yet an engine) ─
    # valuation.py reads `price_data["status"]`, `["last_price"]`, `["date"]`,
    # `["source"]` -- the mock must include those keys.
    def mock_get_price(ticker):
        return {
            "status": "ok",
            "source": "investsite",
            "last_price": 38.5,
            "date": "2024-01-01",
            "market_cap": None,
        }
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation._get_price", mock_get_price)

    return {
        "price": 38.5,
        "shares": 13e9,
        "earnings": 120e9,
        "revenue": 280e9,
        "ebit": 70e9,
        "pl": 350e9,
        "debt": 100e9,
        "cash": 30e9,
        "da": 15e9,
        "fco": 80e9,
        "fci": -30e9,
        "dpa": 1.85,
    }
