"""skills/cvm/valuation/valuation.py -- Valuation ratios combining b3 price + CVM financials.

Computes valuation ratios from local data: b3 price + CVM DFP financials + FRE shares.

[v2.0.0] PHASE 2B REFACTOR -- data fetching now via calculations engines.
  - _get_financials_ttm() (86 lines) REMOVED -> direct engine calls
  - _get_shares_outstanding() (88 lines) REMOVED -> shares_at() engine
  - _get_shares_investsite() + _parse_share_count() REMOVED (shares engine has
    its own investsite fallback built in)
  - _get_price() + 3 helpers KEPT (brapi+investsite+b3 fallback chain not in
    calculations price engine, which is COTAHIST-only)
  - ratios() KEEPS manual ratio computation logic (UNIT ticker handling,
    brapi market_cap, investsite P/L fallback) -- feeds it data from engines
  - ROIC now uses calculations.metrics.roic (actual tax rate from DRE 3.08,
    not the 34% IRPJ+CSLL approximation in v1.0.14)
  - Graham Number now uses calculations.metrics.graham_number (same formula,
    delegated to canonical implementation)
  - NEW ratios added from calculations metrics:
      roe, roa, margem_bruta, margem_operacional, margem_liquida,
      divida_pl, giro_ativos, liquidez_corrente
  - All existing ratio keys preserved (p_l, p_vpa, ev_ebitda, etc.) so
    comparison + screener callers don't break.

[v1.0.14] ROIC + Graham number + TTM valuation + data freshness.
[v1.0.13] Back-calculate market_cap from investsite P/L for unit tickers.
[v1.0.9]  UNIT ticker fix (market-cap-based ratios).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from core.br_validator import validate_ticker

# Phase 2B: calculations engines replace direct data_sources queries.
# Each engine fetches ONE raw quantity at any date; we compose them in ratios().
# Engines are imported at module top (not lazy) -- they are now the core
# dependency of this skill.
from skills.cvm.calculations.engines.earnings import ttm_earnings_at
from skills.cvm.calculations.engines.revenue import revenue_at
from skills.cvm.calculations.engines.ebit import ebit_at
from skills.cvm.calculations.engines.pl import pl_at
from skills.cvm.calculations.engines.debt import debt_at
from skills.cvm.calculations.engines.cash import cash_at
from skills.cvm.calculations.engines.shares import shares_at
from skills.cvm.calculations.engines.da import da_at
from skills.cvm.calculations.engines.operating_cf import operating_cf_at
from skills.cvm.calculations.engines.investing_cf import investing_cf_at
from skills.cvm.calculations.engines.dividends import dividends_at

# Phase 2B: calculations metrics for ROIC + Graham + 8 new fundamental ratios.
# These compose engines internally and handle None/edge cases gracefully.
from skills.cvm.calculations.metrics.roic import roic_at
from skills.cvm.calculations.metrics.graham_number import graham_number_at
from skills.cvm.calculations.metrics.roe import roe_at
from skills.cvm.calculations.metrics.roa import roa_at
from skills.cvm.calculations.metrics.gross_margin import gross_margin_at
from skills.cvm.calculations.metrics.operating_margin import operating_margin_at
from skills.cvm.calculations.metrics.net_margin import net_margin_at
from skills.cvm.calculations.metrics.debt_equity import debt_equity_at
from skills.cvm.calculations.metrics.asset_turnover import asset_turnover_at
from skills.cvm.calculations.metrics.current_ratio import current_ratio_at


def _safe_call(fn: Callable, *args, **kwargs):
    """Call a calculations engine/metric, return None on any exception.

    Calculations engines raise FileNotFoundError when their backing DB is not
    synced (e.g., ITR db missing in test environments). Wrap each call so one
    missing engine doesn't poison the rest of the ratios() result.
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


# ── Mode: ratios (default) ───────────────────────────────────────────────────

def ratios(company: str = "") -> dict:
    """Compute valuation ratios from b3 price + CVM financials + FRE shares.

    [v2.0.0] Data fetching now via calculations engines (Phase 2B refactor):
      - TTM financials (earnings, revenue, ebit, da, FCO, FCI) from engines
      - Snapshot financials (PL, debt, cash, shares) from engines
      - DPA (per-share, TTM) from dividends engine
      - ROIC + Graham Number + 8 new fundamental ratios from calculations metrics

    Returns: P/L, P/VPA, EV, P/EBIT, P/FCO, PSR, EV/EBITDA, DPA, Div Yield,
    ROIC, Graham Number, ROE, ROA, Margins, D/PL, Asset Turnover, Current Ratio,
    Market Cap, + data_freshness.
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
    today = datetime.now().strftime("%Y-%m-%d")
    lucro_liquido = _safe_call(ttm_earnings_at, ticker, today)
    receita_liquida = _safe_call(revenue_at, ticker, today)
    ebit = _safe_call(ebit_at, ticker, today)
    pl = _safe_call(pl_at, ticker, today)
    divida_bruta = _safe_call(debt_at, ticker, today)
    caixa = _safe_call(cash_at, ticker, today)
    da = _safe_call(da_at, ticker, today)
    fco = _safe_call(operating_cf_at, ticker, today)
    fci = _safe_call(investing_cf_at, ticker, today)
    total_shares = _safe_call(shares_at, ticker, today)
    # dividends_at returns DPA per-share (R$/share TTM), NOT total dividends.
    dpa_ttm = _safe_call(dividends_at, ticker, today)

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

    # [v2.0.0] ROIC via calculations metric -- uses ACTUAL tax (DRE 3.08 IR+CSLL),
    # not the 34% IRPJ+CSLL approximation in v1.0.14. Better fidelity.
    # Invested Capital = PL + Debt - Cash (with cash subtraction; v1.9 metric).
    roic_val = _safe_call(roic_at, ticker, today)
    ratios_result["roic"] = roic_val
    # roic_tax_rate is now actual (variable per period) -- not a fixed 0.34.
    # Leave the key as None for backward-compat; consumers should treat as
    # "actual tax used" not "34% approximation".
    ratios_result["roic_tax_rate"] = None

    # [v2.0.0] Graham Number via calculations metric (same formula as v1.0.14,
    # delegated to the canonical implementation in metrics.graham_number).
    ratios_result["graham_number"] = _safe_call(graham_number_at, ticker, today)

    # [v2.0.0] NEW fundamental ratios from calculations metrics.
    # Each composes engines internally and returns None for missing/edge data.
    # All wrapped in _safe_call so a failure in one (e.g., gross_profit not
    # filed for a small-cap) doesn't poison the rest.
    new_metrics: list[tuple[str, Callable]] = [
        ("roe", roe_at),
        ("roa", roa_at),
        ("margem_bruta", gross_margin_at),
        ("margem_operacional", operating_margin_at),
        ("margem_liquida", net_margin_at),
        ("divida_pl", debt_equity_at),
        ("giro_ativos", asset_turnover_at),
        ("liquidez_corrente", current_ratio_at),
    ]
    for key, fn in new_metrics:
        ratios_result[key] = _safe_call(fn, ticker, today)

    result["ratios"] = ratios_result

    # [v1.0.14] Data freshness
    from skills.cvm._freshness import add_freshness
    return add_freshness(result)


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(company: str = "") -> dict:
    """Combined: ratios + data source status (which DBs are synced)."""
    r = ratios(company=company)
    if r.get("status") != "ok":
        return r

    r["data_availability"] = {
        "price": r["sources"].get("price", {}).get("status", "missing"),
        "price_source": r["sources"].get("price", {}).get("source", "unknown"),
        "dfp_ttm": r["sources"].get("financials", {}).get("status", "missing"),
        "fre_shares": r["sources"].get("shares", {}).get("status", "missing"),
    }
    return r


# ── Internal: get price (brapi -> investsite -> b3 trades) ───────────────────
# [v2.0.0] KEPT from v1.0.14 -- calculations price engine uses COTAHIST only
# (historical daily prices). This 3-tier fallback gets the CURRENT price from
# brapi first, then investsite, then b3 trades.db. Will be merged into the
# price engine in a future phase.

def _get_price(ticker: str) -> dict:
    """3-tier price source: brapi -> investsite -> b3 trades."""
    brapi_data = _get_price_brapi(ticker)
    if brapi_data.get("status") == "ok":
        return brapi_data

    investsite_data = _get_price_investsite(ticker)
    if investsite_data.get("status") == "ok":
        return investsite_data

    b3_data = _get_latest_price(ticker)
    if b3_data.get("status") == "ok":
        b3_data["source"] = "b3_trades"
        return b3_data

    investsite_data["source"] = "investsite+b3_trades (both failed)"
    return investsite_data


def _get_price_brapi(ticker: str) -> dict:
    try:
        from data_sources.b3.brapi.query_engine import quote as brapi_quote
        r = brapi_quote(ticker=ticker, force=True)
        if r.get("status") != "ok":
            return {"status": "error", "error": f"brapi: {r.get('error','')}"}
        price = r.get("price")
        if price is None:
            return {"status": "error", "error": "brapi: no price"}
        return {
            "status": "ok", "source": "brapi",
            "last_price": float(price),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "market_cap": r.get("market_cap"),
            "pe_ratio": r.get("pe_ratio"),
        }
    except Exception as e:
        return {"status": "error", "error": f"brapi: {e}"}


def _get_price_investsite(ticker: str) -> dict:
    try:
        from skills.investsite.investsite import indicators
        r = indicators(ticker=ticker)
        if r.get("status") != "ok":
            return {"status": "error", "error": f"investsite: {r.get('error','')}"}

        precos = r.get("sections", {}).get("precos_relativos", {})
        price = precos.get("Preco Atual da Acao")
        date_str = precos.get("Data do Preco da Acao", "")

        if price is None:
            return {"status": "error", "error": "investsite: no price"}

        if not isinstance(price, (int, float)):
            from core.br_validator import parse_brl
            try:
                price = parse_brl(str(price))
            except ValueError:
                return {"status": "error", "error": f"investsite: cannot parse price '{price}'"}

        # [v1.0.12] Extract market cap -- EXACT key match (not substring)
        market_cap = None
        _MCAP_KEYS = {"valor de mercado", "market cap", "valor mercado"}
        for key, raw in precos.items():
            if key.lower().strip() not in _MCAP_KEYS:
                continue
            if isinstance(raw, list) and raw:
                raw = raw[0]
            if isinstance(raw, (int, float)):
                market_cap = float(raw)
            elif isinstance(raw, str):
                from core.br_validator import parse_brl
                try:
                    market_cap = parse_brl(raw)
                except ValueError:
                    pass
            if market_cap is not None and market_cap > 0:
                break

        # [v1.0.10] Extract investsite's pre-computed P/L + P/VPA
        pe_ratio = None
        raw_pe = precos.get("Preco/Lucro")
        if raw_pe is not None and isinstance(raw_pe, (int, float)):
            pe_ratio = float(raw_pe)

        p_vpa_investsite = None
        raw_pvpa = precos.get("Preco/VPA")
        if raw_pvpa is not None and isinstance(raw_pvpa, (int, float)):
            p_vpa_investsite = float(raw_pvpa)

        result = {
            "status": "ok", "source": "investsite",
            "last_price": float(price), "date": date_str,
        }
        if market_cap is not None:
            result["market_cap"] = market_cap
        if pe_ratio is not None:
            result["pe_ratio"] = pe_ratio
        if p_vpa_investsite is not None:
            result["p_vpa"] = p_vpa_investsite
        return result
    except Exception as e:
        return {"status": "error", "error": f"investsite: {e}"}


def _get_latest_price(ticker: str) -> dict:
    """Get latest price from b3 trades.db (fallback)."""
    try:
        import sqlite3
        from data_sources.b3.api.catalog import db_path as b3_db_path
        trades_db = b3_db_path("trades")
        if not trades_db.exists():
            return {"status": "not_synced", "error": "trades.db not found"}
        conn = sqlite3.connect(f"file:{trades_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT RptDt, LastPric FROM trades WHERE TckrSymb=? ORDER BY RptDt DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if not row:
            return {"status": "not_found", "error": f"No trades for {ticker}"}
        return {"status": "ok", "date": row["RptDt"],
                "last_price": float(row["LastPric"]) if row["LastPric"] else None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_div(a: float | None, b: float | None) -> float | None:
    """Divide a/b, returning None when either side is None or b is zero.

    Used by the manual ratio computations in ratios() (market_cap / lucro_liquido,
    etc.). Calculations metrics handle None internally, but the manual ratios
    that compose brapi_market_cap + investsite fallback still need this helper.
    """
    if a is None or b is None or b == 0:
        return None
    return a / b
