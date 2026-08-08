"""Mode: ratios -- valuation ratios combining b3 price + CVM financials.

Computes valuation ratios from local data: b3 price + CVM DFP financials + FRE
shares. Combines a 3-tier price fallback (brapi -> investsite -> b3 trades)
with calculations engines for TTM financials and `compute_all_ratios()` for
the calculations-backed metrics.

[v1.5] REFACTOR -- calculations-backed metrics now come from compute_all_ratios().
  - Removed 25 individual metric imports (roe_at, roa_at, gross_margin_at, etc.)
    + their loops in ratios().
  - Replaced with a single `compute_all_ratios(ticker, today)` call (no
    category filter -- valuation wants everything: profitability, liquidity,
    leverage, efficiency, growth, valuation, per_share, tax).
  - Manual ratio computation (P/L, P/VPA, EV, PSR, DPA, Div Yield, market_cap,
    divida_liquida_ebitda) KEPT -- not in the calculations registry.
  - Manual ROIC + Graham Number calls REMOVED -- they're in the registry and
    come through compute_all_ratios().

[v2.0.0] PHASE 2B REFACTOR -- data fetching now via calculations engines.
  - _get_financials_ttm() removed -> direct engine calls
  - _get_shares_outstanding() removed -> shares_at() engine
  - _get_price() + 3 helpers KEPT in fetchers.py (brapi+investsite+b3 fallback
    chain not in calculations price engine, which is COTAHIST-only).

Registered as "ratios" in skills.cvm.valuation._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.br_validator import validate_ticker

# Phase 2B: calculations engines replace direct data_sources queries.
# Each engine fetches ONE raw quantity at any date; we compose them in ratios().
# Engines are imported at module top (not lazy) -- they are now the core
# dependency of this skill.
from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at
from skills.cvm.calculations.engines.dre.revenue import revenue_at
from skills.cvm.calculations.engines.dre.ebit import ebit_at
from skills.cvm.calculations.engines.bpp.pl import pl_at
from skills.cvm.calculations.engines.bpp.debt import debt_at
from skills.cvm.calculations.engines.bpa.cash import cash_at
from skills.cvm.calculations.engines.shares import shares_at
from skills.cvm.calculations.engines.dfc.da import da_at
from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
from skills.cvm.calculations.engines.dividends import dividends_at

# [v1.5] Single entry point for all calculations-backed metrics.
# compute_all_ratios() walks the registry and returns a flat dict of
# {metric_name: value_or_None} for ALL 37 metrics (no category filter --
# valuation wants everything). New metrics registered via register_metric()
# appear here automatically without touching ratios.py.
from skills.cvm.calculations._registry import compute_all_ratios

from skills.cvm.valuation._registry import register_mode
from skills.cvm.valuation.helpers import _safe_call, _safe_div
from skills.cvm.valuation.fetchers import _get_price


@register_mode(
    "ratios",
    description=(
        "Compute all valuation ratios (P/L, P/VPA, EV, P/EBIT, P/FCO, "
        "P/FCF, EV/EBITDA, EV/Sales, PSR, Div Yield, Market Cap, ROE, ROA, "
        "ROIC, Graham Number, margins, liquidity, leverage, efficiency, "
        "growth) from b3 price + CVM financials + FRE shares."
    ),
    params={
        "company": "str. B3 ticker (PETR4). Required.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="cvm", sub_domain="valuation", mode="ratios", params=\'{"company":"PETR4"}\')',
    ],
)
def ratios(company: str = "") -> dict:
    """Compute valuation ratios from b3 price + CVM financials + FRE shares.

    [v1.5] All calculations-backed metrics now come from compute_all_ratios().
      - Manual ratios (P/L, P/VPA, EV, PSR, DPA, Div Yield, market_cap,
        divida_liquida_ebitda) -- NOT in the calculations registry; computed
        manually from brapi_market_cap + engines.
      - Calculations-backed ratios (ROE, ROA, ROIC, Graham Number, margins,
        turnover, liquidity, EV multiples, per-share, tax, etc.) -- ALL 37
        metrics come from compute_all_ratios(ticker, today) with no category
        filter. New metrics registered via register_metric() appear here
        automatically without touching this file.

    [v2.0.0] Data fetching now via calculations engines (Phase 2B refactor):
      - TTM financials (earnings, revenue, ebit, da, FCO, FCI) from engines
      - Snapshot financials (PL, debt, cash, shares) from engines
      - DPA (per-share, TTM) from dividends engine
      - Manual market-cap-based ratios use brapi_market_cap with UNIT +
        investsite fallback (NOT in the calculations registry).

    Returns: P/L, P/VPA, EV, P/EBIT, P/FCO, PSR, EV/EBITDA, DPA, Div Yield,
    ROIC, Graham Number, ROE, ROA, Margins, D/PL, Asset Turnover, Current
    Ratio, Market Cap, + all 37 calculations-backed metrics + data_freshness.
    """
    if not company:
        return {"status": "error", "error": "company (ticker) is required"}

    ticker = company.strip().upper()
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    result: dict[str, Any] = {
        "status": "ok",
        "ticker": ticker,
        "ratios": {},
        "sources": {},
    }

    # 1. Get latest price (brapi -> investsite -> b3 trades)
    # [v2.0.0] KEPT from v1.0.14 -- calculations price engine is COTAHIST-only,
    # whereas _get_price has brapi+investsite fallback for the CURRENT price.
    price_data = _get_price(ticker)
    result["sources"]["price"] = price_data

    # 2. Get TTM financials via calculations engines [v2.0.0]
    # Each engine fetches ONE quantity at "today" (most recent <= today).
    # _safe_call swallows FileNotFoundError when an underlying DB is missing.
    # [v1.22] Parallel fetch — all 11 engine calls are independent.
    today = datetime.now().strftime("%Y-%m-%d")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as _ex:
        futs = {
            _ex.submit(_safe_call, fn, ticker, today): key
            for key, fn in [
                ("lucro", ttm_earnings_at), ("receita", revenue_at),
                ("ebit", ebit_at), ("pl", pl_at), ("debt", debt_at),
                ("cash", cash_at), ("da", da_at), ("fco", operating_cf_at),
                ("fci", investing_cf_at), ("shares", shares_at),
                ("dpa", dividends_at),
            ]
        }
        _eng = {futs[f]: f.result() for f in futs}
    lucro_liquido = _eng.get("lucro")
    receita_liquida = _eng.get("receita")
    ebit = _eng.get("ebit")
    pl = _eng.get("pl")
    divida_bruta = _eng.get("debt")
    caixa = _eng.get("cash")
    da = _eng.get("da")
    fco = _eng.get("fco")
    fci = _eng.get("fci")
    total_shares = _eng.get("shares")
    # dividends_at returns DPA per-share (R$/share TTM), NOT total dividends.
    dpa_ttm = _eng.get("dpa")

    # EBITDA = EBIT + D&A (only computable when both are present)
    ebitda = (ebit + da) if (ebit is not None and da is not None) else None

    # Backward-compat: derive annual_dividends (BRL total) from per-share DPA.
    # Original v1.0.14 got "proventos" as a BRL total from financials skill.
    if dpa_ttm is not None and total_shares:
        annual_dividends = dpa_ttm * total_shares
    else:
        annual_dividends = None

    # Aggregate status for sources/financials (used by summary())
    fin_any = any(v is not None for v in (
        lucro_liquido, pl, ebit, ebitda, fco, fci,
        receita_liquida, caixa, divida_bruta,
    ))
    fin_status = "ok" if fin_any else "not_found"

    result["sources"]["financials"] = {
        "status": fin_status,
        "period": "ttm",
        "source": "calculations_engines",
        "error": "" if fin_any else "No data from calculations engines",
        "lucro_liquido": lucro_liquido,
        "patrimonio_liquido": pl,
        "ebitda": ebitda,
        "ebitda_method": "ebit+da" if ebitda is not None else None,
    }

    # 3. Shares source info [v2.0.0] -- shares_at engine has investsite fallback built in
    result["sources"]["shares"] = {
        "status": "ok" if total_shares else "not_found",
        "total_shares": total_shares,
        "error": "" if total_shares else "No share data",
        # on_shares/pn_shares not exposed by calculations shares_at (it returns only total)
        "on_shares": None,
        "pn_shares": None,
        "source": "calculations_engine",
    }

    # If price is missing, we can't compute any ratios
    if price_data.get("status") != "ok":
        result["ratios"] = {"status": "error",
                            "error": f"Price unavailable: {price_data.get('error','')}"}
        from skills.cvm._freshness import add_freshness
        return add_freshness(result)

    price = price_data["last_price"]
    price_date = price_data["date"]

    # [v1.0.9] Detect UNIT tickers
    unit_ticker = ticker.upper().endswith("11")

    # [v1.0.9-v1.0.13] Market cap resolution
    brapi_market_cap = price_data.get("market_cap")

    # If financials are missing, partial result
    if fin_status != "ok":
        result["ratios"] = {"status": "partial",
                            "price": price, "price_date": price_date,
                            "unit_ticker": unit_ticker,
                            "note": "Financials unavailable: no data from calculations engines"}
        if brapi_market_cap is not None:
            result["ratios"]["market_cap"] = float(brapi_market_cap)
            result["ratios"]["market_cap_source"] = "brapi"
        elif total_shares and total_shares > 0:
            result["ratios"]["market_cap"] = price * total_shares
            result["ratios"]["market_cap_source"] = "computed"
        if total_shares:
            result["ratios"]["total_shares"] = total_shares
        from skills.cvm._freshness import add_freshness
        return add_freshness(result)

    pl_positive = pl is not None and pl > 0

    ratios_result: dict[str, Any] = {
        "price": price,
        "price_date": price_date,
        "price_source": price_data.get("source", "?"),
        "unit_ticker": unit_ticker,
        "total_shares": total_shares,
        "lucro_liquido": lucro_liquido,
        "patrimonio_liquido": pl,
        "ebit": ebit,
        "ebitda": ebitda,
        "ebitda_method": "ebit+da" if ebitda is not None else None,
        "fco": fco,
        "fci": fci,
        "receita_liquida": receita_liquida,
        "caixa": caixa,
        "divida_bruta": divida_bruta,
        "annual_dividends": annual_dividends,
    }

    # [v1.0.9-v1.0.13] Market cap resolution
    if brapi_market_cap is not None:
        market_cap = float(brapi_market_cap)
        ratios_result["market_cap"] = market_cap
        ratios_result["market_cap_source"] = "brapi" if price_data.get("source") == "brapi" else "investsite"
    elif total_shares and total_shares > 0:
        market_cap = price * total_shares
        ratios_result["market_cap"] = market_cap
        ratios_result["market_cap_source"] = "computed"
    else:
        market_cap = None
        ratios_result["market_cap"] = None
        ratios_result["market_cap_source"] = "none"

    # [v1.0.10-v1.0.13] investsite fallback for unit tickers
    investsite_pe = price_data.get("pe_ratio")
    investsite_pvpa = price_data.get("p_vpa")
    use_investsite_ratios = (unit_ticker
                             and ratios_result["market_cap_source"] == "computed"
                             and investsite_pe is not None)

    # EPS + VPA (per-individual-share, informational)
    eps = _safe_div(lucro_liquido, total_shares)
    ratios_result["eps"] = eps
    vpa = _safe_div(pl, total_shares)
    ratios_result["vpa"] = vpa

    # P/L, P/VPA -- market-cap-based (v1.0.9) or investsite fallback (v1.0.10)
    if use_investsite_ratios:
        if investsite_pe is not None and lucro_liquido is not None and lucro_liquido > 0:
            market_cap = investsite_pe * lucro_liquido
            ratios_result["market_cap"] = market_cap
            ratios_result["market_cap_source"] = "investsite_derived"
        ratios_result["p_l"] = investsite_pe
        ratios_result["p_vpa"] = investsite_pvpa if (pl_positive and investsite_pvpa is not None) else None
        ratios_result["p_l_source"] = "investsite"
    else:
        ratios_result["p_l"] = _safe_div(market_cap, lucro_liquido)
        ratios_result["p_vpa"] = _safe_div(market_cap, pl) if pl_positive else None
        ratios_result["p_l_source"] = "computed"

    # EV = Market Cap + Debt - Cash
    divida_liquida = None
    if market_cap is not None and divida_bruta is not None and caixa is not None:
        divida_liquida = divida_bruta - caixa
        ratios_result["ev"] = market_cap + divida_liquida
    elif market_cap is not None:
        ratios_result["ev"] = market_cap
    else:
        ratios_result["ev"] = None

    ratios_result["p_ebit"] = _safe_div(market_cap, ebit)
    ratios_result["p_fco"] = _safe_div(market_cap, fco)
    ratios_result["psr"] = _safe_div(market_cap, receita_liquida)
    ratios_result["ev_ebitda"] = _safe_div(ratios_result["ev"], ebitda)

    fcf = None
    if fco is not None and fci is not None:
        fcf = fco + fci
    ratios_result["fcf"] = fcf
    ratios_result["p_fcf"] = _safe_div(market_cap, fcf)

    # [v2.0.0] DPA + Div Yield -- dividends_at returns DPA per-share directly.
    # (v1.0.14 derived DPA = annual_dividends / shares; we now skip that step.)
    ratios_result["dpa"] = dpa_ttm
    ratios_result["dividend_yield"] = _safe_div(dpa_ttm, price)

    ratios_result["divida_liquida_ebitda"] = _safe_div(divida_liquida, ebitda)

    # [v1.5] ALL calculations-backed ratios via the registry's single entry point.
    # compute_all_ratios() walks the METRICS dict (auto-discovered from metrics/*.py)
    # and returns {metric_name: value_or_None} for ALL 37 metrics, no category
    # filter -- valuation wants everything: profitability, liquidity, leverage,
    # efficiency, growth, valuation, per_share, tax. New metrics registered via
    # register_metric() appear here automatically without touching this file.
    #
    # NOTE: this OVERRIDES some of the manual computations above for keys that
    # exist in BOTH places (ev_ebitda, p_ebit, p_fco, p_fcf, vpa, dpa). The
    # registry uses COTAHIST price * FRE shares for market cap; the manual
    # computations above use brapi_market_cap with investsite/UNIT fallback.
    # The registry versions win (canonical implementation). Manual keys that
    # have NO registry counterpart (p_l, p_vpa, ev, psr, dividend_yield,
    # divida_liquida_ebitda, market_cap) are preserved as-is.
    calc_ratios = compute_all_ratios(ticker, today)
    ratios_result.update(calc_ratios)

    # [v1.5] Preserve manual per-share values that compute_all_ratios overwrites.
    # compute_all_ratios calls ratio_fn (not per_share_fn) for Type 1 metrics,
    # so "vpa" gets P/VPA (ratio), "dpa" gets Div Yield (ratio), "lpa" gets P/E
    # (ratio), and "rps" gets P/S (ratio). But the manual code above sets these
    # to their per-share values. Restore them -- the ratios are available under
    # their own keys (pvpa, dy, pe, psr) from the registry.
    ratios_result["vpa"] = vpa  # per-share VPA (PL / shares)
    ratios_result["dpa"] = dpa_ttm  # per-share DPA (dividends per share TTM)
    ratios_result["lpa"] = eps  # per-share LPA (earnings / shares)
    ratios_result["rps"] = _safe_div(receita_liquida, total_shares)  # per-share RPS

    # [v1.5] Backward-compatibility aliases: Portuguese keys that comparison +
    # screener skills read. These map to the canonical English registry keys.
    # The registry returns English keys (gross_margin, debt_equity, etc.) but
    # downstream skills were wired with Portuguese keys in v1.2-v1.4. These
    # aliases ensure backward compat -- both English and Portuguese keys work.
    _pt_aliases = {
        "margem_bruta": "gross_margin",
        "margem_operacional": "operating_margin",
        "margem_liquida": "net_margin",
        "divida_pl": "debt_equity",
        "giro_ativos": "asset_turnover",
        "liquidez_corrente": "current_ratio",
    }
    for pt_key, en_key in _pt_aliases.items():
        if pt_key not in ratios_result and en_key in calc_ratios:
            ratios_result[pt_key] = calc_ratios[en_key]

    # roic_tax_rate is no longer computed manually (was 0.34 in v1.0.14, then
    # set to None in v2.0.0 when ROIC moved to the actual-tax metric). Kept
    # for backward-compat with consumers that read this key.
    ratios_result.setdefault("roic_tax_rate", None)

    result["ratios"] = ratios_result

    # [v1.0.14] Data freshness
    from skills.cvm._freshness import add_freshness
    return add_freshness(result)
