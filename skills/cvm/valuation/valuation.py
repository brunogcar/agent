"""skills/cvm/valuation/valuation.py -- Valuation ratios combining b3 price + CVM financials.

Computes valuation ratios from local data: b3 price + CVM DFP financials + FRE shares.

v1.0.14: ROIC + Graham number + TTM valuation + data freshness.
v1.0.13: Back-calculate market_cap from investsite P/L for unit tickers.
v1.0.9:  UNIT ticker fix (market-cap-based ratios).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.br_validator import validate_ticker

from data_sources.cvm._db import connect_dfp, connect_fre, parse_escala
from data_sources.cvm._bridge import resolve_company


# ── Mode: ratios (default) ───────────────────────────────────────────────────

def ratios(company: str = "") -> dict:
    """Compute valuation ratios from b3 price + CVM financials + FRE shares.

    [v1.0.14] Now uses TTM (trailing twelve months) financials instead of
    latest annual DFP. More current — reflects the last 4 quarters, not the
    last fiscal year. Also adds ROIC + Graham number.

    Returns: P/L, P/VPA, EV, P/EBIT, P/FCO, Dividend Yield, Market Cap,
    ROIC, Graham Number, + data_freshness.
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

    # 1. Get latest price
    price_data = _get_price(ticker)
    result["sources"]["price"] = price_data

    # 2. Get TTM financials [v1.0.14] — was annual, now quarterly TTM
    #    Call via _get_financials (alias) so existing test mocks work.
    fin_data = _get_financials(ticker)
    result["sources"]["financials"] = {
        "status": fin_data.get("status"),
        "period": fin_data.get("period"),
        "source": fin_data.get("source", "ttm"),
        "error": fin_data.get("error", ""),
        "lucro_liquido": fin_data.get("lucro_liquido"),
        "patrimonio_liquido": fin_data.get("patrimonio_liquido"),
        "ebitda": fin_data.get("ebitda"),
        "ebitda_method": fin_data.get("ebitda_method"),
    }

    # 3. Get shares outstanding from FRE
    shares_data = _get_shares_outstanding(ticker)
    result["sources"]["shares"] = {
        "status": shares_data.get("status"),
        "total_shares": shares_data.get("total_shares"),
        "error": shares_data.get("error", ""),
        "on_shares": shares_data.get("on_shares"),
        "pn_shares": shares_data.get("pn_shares"),
        "source": shares_data.get("source", "?"),
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
    if fin_data.get("status") != "ok":
        result["ratios"] = {"status": "partial",
                            "price": price, "price_date": price_date,
                            "unit_ticker": unit_ticker,
                            "note": f"Financials unavailable: {fin_data.get('error','')}"}
        total_shares = shares_data.get("total_shares")
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

    # Extract financials
    lucro_liquido = fin_data.get("lucro_liquido")
    pl = fin_data.get("patrimonio_liquido")
    ebit = fin_data.get("ebit")
    ebitda = fin_data.get("ebitda")
    fco = fin_data.get("fco")
    fci = fin_data.get("fci")
    receita_liquida = fin_data.get("receita_liquida")
    caixa = fin_data.get("caixa")
    divida_bruta = fin_data.get("divida_bruta")
    total_shares = shares_data.get("total_shares")
    annual_dividends = fin_data.get("proventos")

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
        "ebitda_method": fin_data.get("ebitda_method"),
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

    # P/L, P/VPA — market-cap-based (v1.0.9) or investsite fallback (v1.0.10)
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

    if annual_dividends is not None and total_shares and total_shares > 0:
        dpa = annual_dividends / total_shares
        ratios_result["dpa"] = dpa
        ratios_result["dividend_yield"] = _safe_div(dpa, price)
    else:
        ratios_result["dpa"] = None
        ratios_result["dividend_yield"] = None

    ratios_result["divida_liquida_ebitda"] = _safe_div(divida_liquida, ebitda)

    # [v1.0.14] ROIC = NOPAT / Invested Capital
    # NOPAT = EBIT x (1 - tax_rate). Brazil: IRPJ 25% + CSLL 9% = 34% combined.
    # Invested Capital = PL + Divida Bruta - Caixa (simplified).
    # Flag as approximate -- actual tax rate varies.
    if ebit is not None and pl is not None and divida_bruta is not None and caixa is not None:
        tax_rate = 0.34  # Brazilian combined corporate tax (IRPJ + CSLL)
        nopat = ebit * (1 - tax_rate)
        invested_capital = pl + divida_bruta - caixa
        if invested_capital > 0:
            ratios_result["roic"] = nopat / invested_capital
            ratios_result["roic_tax_rate"] = 0.34  # flag: approximate
        else:
            ratios_result["roic"] = None
            ratios_result["roic_tax_rate"] = None
    else:
        ratios_result["roic"] = None
        ratios_result["roic_tax_rate"] = None

    # [v1.0.14] Graham number = sqrt(22.5 x EPS x VPA)
    # Only valid when EPS > 0 and VPA > 0 (Graham's original constraint).
    if eps is not None and vpa is not None and eps > 0 and vpa > 0:
        ratios_result["graham_number"] = (22.5 * eps * vpa) ** 0.5
    else:
        ratios_result["graham_number"] = None

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


# ── Internal: get TTM financials [v1.0.14] ───────────────────────────────────

def _get_financials_ttm(ticker: str) -> dict:
    """[v1.0.14] Get TTM financials by calling financials.quarterly().

    Uses the TTM summary (sum of last 4 standalone quarters for flows,
    average for snapshots). More current than annual DFP.
    """
    try:
        from skills.cvm.financials.financials import quarterly
        r = quarterly(company=ticker, periods=8, consolidado=1)
        if r.get("status") != "ok":
            return {"status": "not_found", "error": r.get("error", "No quarterly data")}

        ttm = r.get("ttm", {})
        if ttm.get("status") != "ok":
            # TTM not available -- fall back to latest annual period
            if not r.get("periods"):
                return {"status": "not_found", "error": "No periods"}
            p = r["periods"][0]
            m = p.get("metrics", {}) or {}
            return {
                "status": "ok", "source": "annual_fallback",
                "period": p.get("period", ""),
                "lucro_liquido": m.get("lucro_liquido"),
                "patrimonio_liquido": m.get("patrimonio_liquido"),
                "ebit": m.get("ebit"),
                "ebitda": m.get("ebitda"),
                "ebitda_method": m.get("ebitda_method"),
                "fco": m.get("fco"),
                "fci": m.get("fci"),
                "receita_liquida": m.get("receita_liquida"),
                "caixa": m.get("caixa"),
                "divida_bruta": m.get("divida_bruta"),
                "proventos": m.get("proventos"),
            }

        m = ttm.get("metrics", {}) or {}

        # [v1.0.14a] If TTM key metrics (lucro_liquido, ebitda) are None, it
        # means at least one of the 4 quarters is missing that value. Fall back
        # to financials.annual() — annual DFP always has these values.
        if m.get("lucro_liquido") is None or m.get("ebitda") is None:
            try:
                from skills.cvm.financials.financials import annual
                ar = annual(company=ticker, periods=1, consolidado=1)
                if ar.get("status") == "ok" and ar.get("periods"):
                    p = ar["periods"][0]  # annual periods are newest-first
                    am = p.get("metrics", {}) or {}
                    if am.get("lucro_liquido") is not None or am.get("ebitda") is not None:
                        return {
                            "status": "ok", "source": "annual_fallback_from_ttm",
                            "period": p.get("period", "") + " (annual — TTM had None)",
                            "lucro_liquido": am.get("lucro_liquido"),
                            "patrimonio_liquido": am.get("patrimonio_liquido"),
                            "ebit": am.get("ebit"),
                            "ebitda": am.get("ebitda"),
                            "ebitda_method": am.get("ebitda_method"),
                            "fco": am.get("fco"),
                            "fci": am.get("fci"),
                            "receita_liquida": am.get("receita_liquida"),
                            "caixa": am.get("caixa"),
                            "divida_bruta": am.get("divida_bruta"),
                            "proventos": am.get("proventos"),
                        }
            except Exception:
                pass

        return {
            "status": "ok", "source": "ttm",
            "period": ttm.get("period_range", ""),
            "lucro_liquido": m.get("lucro_liquido"),
            "patrimonio_liquido": m.get("patrimonio_liquido"),
            "ebit": m.get("ebit"),
            "ebitda": m.get("ebitda"),
            "ebitda_method": m.get("ebitda_method"),
            "fco": m.get("fco"),
            "fci": m.get("fci"),
            "receita_liquida": m.get("receita_liquida"),
            "caixa": m.get("caixa"),
            "divida_bruta": m.get("divida_bruta"),
            "proventos": m.get("proventos"),
        }
    except Exception as e:
        return {"status": "error", "error": f"financials: {e}"}


# ── Internal: get shares outstanding from FRE ────────────────────────────────

def _get_shares_outstanding(ticker: str) -> dict:
    """Get total shares from FRE distribuicao_capital + investsite fallback."""
    try:
        conn = connect_fre(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        from data_sources.cvm._bridge import _resolve_via_bridge, _auto_sync_bridge
        cnpj, _ = _resolve_via_bridge(ticker)
        if not cnpj:
            if _auto_sync_bridge(ticker):
                cnpj, _ = _resolve_via_bridge(ticker)
        if not cnpj:
            return {"status": "not_found", "error": f"Ticker '{ticker}' not in bridge.db"}

        row = conn.execute(
            "SELECT qtd_on_circulacao, qtd_pn_circulacao, qtd_total_circulacao, "
            "data_referencia FROM distribuicao_capital "
            "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '')=? "
            "ORDER BY data_referencia DESC LIMIT 1",
            (cnpj,),
        ).fetchone()

        total = None
        on_shares = None
        pn_shares = None
        data_ref = ""

        if row:
            total = row["qtd_total_circulacao"] if row["qtd_total_circulacao"] else None
            on_shares = row["qtd_on_circulacao"] if row["qtd_on_circulacao"] else None
            pn_shares = row["qtd_pn_circulacao"] if row["qtd_pn_circulacao"] else None
            data_ref = row["data_referencia"] or ""
            if not total and (on_shares or pn_shares):
                total = (on_shares or 0) + (pn_shares or 0)

        shares_source = "fre_distribuicao"
        if not total:
            try:
                row2 = conn.execute(
                    "SELECT * FROM capital_social "
                    "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '')=? "
                    "ORDER BY data_referencia DESC LIMIT 1",
                    (cnpj,),
                ).fetchone()
                if row2:
                    shares_source = "fre_capital_social"
                    for key in ["qtd_total", "total_shares", "quantidade_total"]:
                        if key in row2.keys() and row2[key]:
                            total = int(row2[key])
                            break
                    if "data_referencia" in row2.keys():
                        data_ref = row2["data_referencia"] or data_ref
            except Exception:
                pass

        conn.close()

        if not total:
            investsite_shares = _get_shares_investsite(ticker)
            if investsite_shares.get("total_shares"):
                return {
                    "status": "ok",
                    "total_shares": investsite_shares["total_shares"],
                    "on_shares": investsite_shares.get("on_shares"),
                    "pn_shares": investsite_shares.get("pn_shares"),
                    "data_referencia": investsite_shares.get("data_referencia", ""),
                    "source": "investsite",
                }

        if not total:
            return {"status": "not_found", "error": f"No share data for {ticker}"}

        return {
            "status": "ok",
            "total_shares": int(total) if total else None,
            "on_shares": int(on_shares) if on_shares else None,
            "pn_shares": int(pn_shares) if pn_shares else None,
            "data_referencia": data_ref,
            "source": shares_source,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


def _get_shares_investsite(ticker: str) -> dict:
    try:
        from skills.investsite.investsite import indicators
        r = indicators(ticker=ticker)
        if r.get("status") != "ok":
            return {"status": "error", "error": "investsite indicators failed"}
        balanco = r.get("sections", {}).get("balanco_patrimonial", {})
        total_str = balanco.get("Total")
        on_str = balanco.get("Acoes Ordinarias")
        pn_str = balanco.get("Acoes Preferenciais")
        total = _parse_share_count(total_str) if total_str else None
        on_shares = _parse_share_count(on_str) if on_str else None
        pn_shares = _parse_share_count(pn_str) if pn_str else None
        return {"status": "ok" if total else "not_found",
                "total_shares": total, "on_shares": on_shares, "pn_shares": pn_shares,
                "data_referencia": "", "source": "investsite"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _parse_share_count(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    clean = str(value).strip().replace(".", "").replace(",", "")
    try:
        return int(clean)
    except ValueError:
        try:
            return int(float(clean))
        except ValueError:
            return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# [v1.0.14] Backward-compat alias — tests mock _get_financials (old name).
# _get_financials_ttm is the v1.0.14 name; keep both so existing tests work.
_get_financials = _get_financials_ttm
