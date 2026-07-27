"""Shared fixtures for the valuation skill tests.

[Phase 2C] Valuation now consumes calculations engines + metrics (Phase 2B
refactor). The old fixture built synthetic DFP/FRE/trades DBs and patched
internal helpers (`_get_shares_investsite`, `_get_financials`) that no longer
exist. The new fixture mocks the engine/metric functions at the names bound
inside `skills.cvm.valuation.valuation` (which imports them via
`from <engine_module> import <fn>` -- the bound names are what the SUT actually
calls, so that is the namespace we must patch).

Env vars (PLANNER_MODEL etc.) are set by the parent conftest at
``tests/skills/cvm/conftest.py``.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def valuation_env(monkeypatch):
    """Mock calculations engines + metrics + price for valuation.ratios().

    All engine/metric functions are patched at the names bound inside
    ``skills.cvm.valuation.valuation`` (NOT at their source modules), because
    valuation.py imports them via ``from <module> import <fn>``. Patching the
    source module would not affect the local references already bound in
    valuation.valuation's namespace.

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
      vpa         = 350e9 / 13e9             ≈ 26.92
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

    Metrics (mocked directly):
      roic=0.18, graham_number=75.0, roe=0.28, roa=0.15,
      gross_margin=0.35, operating_margin=0.25, net_margin=0.20,
      debt_equity=0.29, asset_turnover=0.35, current_ratio=1.5
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

    # ── Calculations metrics (composed ratios called by valuation) ────────
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.roic_at", lambda c, d: 0.18)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.graham_number_at", lambda c, d: 75.0)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.roe_at", lambda c, d: 0.28)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.roa_at", lambda c, d: 0.15)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.gross_margin_at", lambda c, d: 0.35)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.operating_margin_at", lambda c, d: 0.25)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.net_margin_at", lambda c, d: 0.20)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.debt_equity_at", lambda c, d: 0.29)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.asset_turnover_at", lambda c, d: 0.35)
    monkeypatch.setattr(
        "skills.cvm.valuation.valuation.current_ratio_at", lambda c, d: 1.5)

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
