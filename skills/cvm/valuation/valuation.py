"""skills/cvm/valuation/valuation.py -- Valuation ratios combining b3 price + CVM financials.

Computes the "goldmine" indicators from investsite, but from our local data:
  - Market Cap = price × shares outstanding
  - P/L (P/E) = price / EPS
  - P/VPA (P/B) = price / VPA
  - EV = Market Cap + Debt - Cash
  - P/EBIT = price / (EBIT / shares)
  - P/FCO = price / (FCO / shares)
  - Dividend Yield = annual dividends / price

DATA SOURCES
-------------
  - b3/api (trades.db): LastPric (latest price)
  - cvm/dfp (dfp.db): latest annual financials (lucro líquido, PL, EBIT, FCO, dívida, caixa)
  - cvm/fre (fre.db): distribuicao_capital table (shares outstanding — ON/PN/total)
  - cvm/bridge: ticker → CNPJ → empresa_ids

RESOLUTION
----------
All modes accept `company` (ticker preferred). The bridge auto-syncs.
If b3 trades.db or fre.db is not synced, the ratio is returned as None
with a note explaining what's missing.

USES core/br_validator
----------------------
All value parsing uses parse_escala, validate_ticker from core/br_validator.py.
Financial skills MUST use br_validator for consistent BRL/date/ticker handling.
"""

from __future__ import annotations

from typing import Any

from core.br_validator import validate_ticker

from data_sources.cvm._db import connect_dfp, connect_fre, parse_escala
from data_sources.cvm._bridge import resolve_company


# ── Mode: ratios (default) ───────────────────────────────────────────────────

def ratios(company: str = "") -> dict:
    """Compute valuation ratios from b3 price + CVM financials + FRE shares.

    Returns: P/L, P/VPA, EV, P/EBIT, P/FCO, Dividend Yield, Market Cap.
    Each ratio includes the underlying values used (price, EPS, VPA, etc.)
    so the caller can verify.
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

    # [v1.0.2] Fetch ALL 3 sources first (best-effort), then compute ratios.
    # Price: investsite primary (live, always available), b3 trades.db fallback.

    # 1. Get latest price — try investsite first, then b3 trades.db
    price_data = _get_price(ticker)
    result["sources"]["price"] = price_data

    # 2. Get latest annual financials from DFP
    fin_data = _get_latest_financials(ticker)
    result["sources"]["financials"] = {
        "status": fin_data.get("status"),
        "ano": fin_data.get("ano"),
        "error": fin_data.get("error", ""),
        # [v1.0.4] Include actual values for diagnostics
        "lucro_liquido": fin_data.get("lucro_liquido"),
        "patrimonio_liquido": fin_data.get("patrimonio_liquido"),
        "empresa_ids_found": fin_data.get("empresa_ids_count", 0),
        "rows_found": fin_data.get("rows_found", 0),
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

    # If price is missing, we can't compute any ratios — return with source status
    if price_data.get("status") != "ok":
        result["ratios"] = {"status": "error",
                            "error": f"Price unavailable: {price_data.get('error','')}",
                            "note": "Sync b3 trades.db: data_source(domain='b3', sub_domain='api', mode='sync', params='{\"table\":\"trades\"}')"}
        return result

    price = price_data["last_price"]
    price_date = price_data["date"]

    # If financials are missing, we can compute Market Cap but not P/L etc.
    if fin_data.get("status") != "ok":
        result["ratios"] = {"status": "partial",
                            "price": price,
                            "price_date": price_date,
                            "note": f"Financials unavailable: {fin_data.get('error','')}. Only price-based metrics available."}
        # Still compute Market Cap if shares are available
        total_shares = shares_data.get("total_shares")
        if total_shares and total_shares > 0:
            result["ratios"]["market_cap"] = price * total_shares
            result["ratios"]["total_shares"] = total_shares
        return result

    # Compute ratios
    lucro_liquido = fin_data.get("lucro_liquido")
    pl = fin_data.get("patrimonio_liquido")
    ebit = fin_data.get("ebit")
    fco = fin_data.get("fco")
    caixa = fin_data.get("caixa")
    divida_bruta = fin_data.get("divida_bruta")
    total_shares = shares_data.get("total_shares")
    annual_dividends = fin_data.get("proventos")  # DVA 7.08.04

    ratios_result: dict[str, Any] = {
        "price": price,
        "price_date": price_date,
        "total_shares": total_shares,
        "lucro_liquido": lucro_liquido,
        "patrimonio_liquido": pl,
        "ebit": ebit,
        "fco": fco,
        "caixa": caixa,
        "divida_bruta": divida_bruta,
        "annual_dividends": annual_dividends,
    }

    # Market Cap = price × shares
    if total_shares and total_shares > 0:
        ratios_result["market_cap"] = price * total_shares
    else:
        ratios_result["market_cap"] = None

    # EPS = lucro_liquido / shares
    eps = _safe_div(lucro_liquido, total_shares)
    ratios_result["eps"] = eps

    # P/L = price / EPS
    ratios_result["p_l"] = _safe_div(price, eps)

    # VPA = PL / shares
    vpa = _safe_div(pl, total_shares)
    ratios_result["vpa"] = vpa

    # P/VPA = price / VPA
    ratios_result["p_vpa"] = _safe_div(price, vpa)

    # EV = Market Cap + Debt - Cash
    if ratios_result["market_cap"] is not None and divida_bruta is not None and caixa is not None:
        ratios_result["ev"] = ratios_result["market_cap"] + divida_bruta - caixa
    elif ratios_result["market_cap"] is not None:
        ratios_result["ev"] = ratios_result["market_cap"]  # partial
    else:
        ratios_result["ev"] = None

    # P/EBIT = price / (EBIT / shares)
    ebit_per_share = _safe_div(ebit, total_shares)
    ratios_result["p_ebit"] = _safe_div(price, ebit_per_share)

    # P/FCO = price / (FCO / shares)
    fco_per_share = _safe_div(fco, total_shares)
    ratios_result["p_fco"] = _safe_div(price, fco_per_share)

    # Dividend Yield = annual dividends / price (per share)
    if annual_dividends is not None and total_shares and total_shares > 0:
        div_per_share = annual_dividends / total_shares
        ratios_result["dividend_yield"] = _safe_div(div_per_share, price)
        ratios_result["div_per_share"] = div_per_share
    else:
        ratios_result["dividend_yield"] = None
        ratios_result["div_per_share"] = None

    result["ratios"] = ratios_result
    return result


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(company: str = "") -> dict:
    """Combined: ratios + data source status (which DBs are synced)."""
    r = ratios(company=company)
    if r.get("status") != "ok":
        return r

    r["data_availability"] = {
        "price": r["sources"].get("price", {}).get("status", "missing"),
        "price_source": r["sources"].get("price", {}).get("source", "unknown"),
        "dfp_annual": r["sources"].get("financials", {}).get("status", "missing"),
        "fre_shares": r["sources"].get("shares", {}).get("status", "missing"),
    }
    return r


# ── Internal: get price (brapi primary → investsite → b3 trades fallback) ────

def _get_price(ticker: str) -> dict:
    """Get latest price for a ticker.

    [v1.0.7] 3-tier price source:
    1. brapi.dev (proper API, 15-min delay, returns price + market_cap + PE)
    2. investsite.com.br (web scraping, always available)
    3. b3 trades.db (local, D+1 delay, when synced)

    Returns dict with: status, source, last_price, date.
    """
    # 1. Try brapi.dev first (best — proper API, fast, 15-min delay)
    brapi_data = _get_price_brapi(ticker)
    if brapi_data.get("status") == "ok":
        return brapi_data

    # 2. Fallback: investsite (web scraping, always available)
    investsite_data = _get_price_investsite(ticker)
    if investsite_data.get("status") == "ok":
        return investsite_data

    # 3. Fallback: b3 trades.db (local, D+1)
    b3_data = _get_latest_price(ticker)
    if b3_data.get("status") == "ok":
        b3_data["source"] = "b3_trades"
        return b3_data

    # Both failed — return investsite error (more helpful message)
    investsite_data["source"] = "investsite+b3_trades (both failed)"
    return investsite_data


def _get_price_brapi(ticker: str) -> dict:
    """Get latest price from brapi.dev (proper API, 15-min delay).

    brapi.dev returns: regularMarketPrice, marketCap, priceEarnings, volume.
    Free tier covers PETR4, VALE3, ITUB4, MGLU3 without token.
    """
    try:
        from data_sources.b3.brapi.query_engine import quote as brapi_quote
        r = brapi_quote(ticker=ticker, force=True)
        if r.get("status") != "ok":
            return {"status": "error", "error": f"brapi: {r.get('error','')}"}

        price = r.get("price")
        if price is None:
            return {"status": "error", "error": "brapi: no price in response"}

        return {
            "status": "ok",
            "source": "brapi",
            "last_price": float(price),
            "date": "",  # brapi doesn't return date in quote mode
            "market_cap": r.get("market_cap"),
            "pe_ratio": r.get("pe_ratio"),
        }
    except Exception as e:
        return {"status": "error", "error": f"brapi: {e}"}


def _get_price_investsite(ticker: str) -> dict:
    """Get latest price from investsite.com.br (live web scraping).

    Uses the investsite skill's indicators mode, which returns
    'Preco Atual da Acao' in the precos_relativos section.
    """
    try:
        from skills.investsite.investsite import indicators
        r = indicators(ticker=ticker)
        if r.get("status") != "ok":
            return {"status": "error",
                    "error": f"investsite: {r.get('error', 'unknown')}"}

        precos = r.get("sections", {}).get("precos_relativos", {})
        price = precos.get("Preco Atual da Acao")
        date_str = precos.get("Data do Preco da Acao", "")

        if price is None:
            return {"status": "error",
                    "error": "investsite: Preco Atual da Acao not found"}

        # price is already parsed to float by _try_parse_brl in investsite parsers
        if not isinstance(price, (int, float)):
            # If it's still a string, parse it
            from core.br_validator import parse_brl
            try:
                price = parse_brl(str(price))
            except ValueError:
                return {"status": "error",
                        "error": f"investsite: cannot parse price '{price}'"}

        return {
            "status": "ok",
            "source": "investsite",
            "last_price": float(price),
            "date": date_str,
        }
    except Exception as e:
        return {"status": "error",
                "error": f"investsite: {e}"}



def _get_shares_investsite(ticker: str) -> dict:
    """Get shares outstanding from investsite (balanco_patrimonial section).

    investsite's indicators page has a 'Resumo Balanco Patrimonial' table
    with 'Total' (total shares), 'Acoes Ordinarias', 'Acoes Preferenciais'.
    """
    try:
        from skills.investsite.investsite import indicators
        r = indicators(ticker=ticker)
        if r.get("status") != "ok":
            return {"status": "error", "error": "investsite indicators failed"}

        balanco = r.get("sections", {}).get("balanco_patrimonial", {})

        # Keys are ASCII-normalized by investsite parser
        total_str = balanco.get("Total")
        on_str = balanco.get("Acoes Ordinarias")
        pn_str = balanco.get("Acoes Preferenciais")

        total = _parse_share_count(total_str) if total_str else None
        on_shares = _parse_share_count(on_str) if on_str else None
        pn_shares = _parse_share_count(pn_str) if pn_str else None

        return {
            "status": "ok" if total else "not_found",
            "total_shares": total,
            "on_shares": on_shares,
            "pn_shares": pn_shares,
            "data_referencia": "",
            "source": "investsite",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _parse_share_count(value) -> int | None:
    """Parse a share count string like '12.888.732.761' to int."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    # Remove dots (thousands separator in BR format) and parse
    clean = str(value).strip().replace(".", "").replace(",", "")
    try:
        return int(clean)
    except ValueError:
        try:
            return int(float(clean))
        except ValueError:
            return None


# ── Internal: get latest price from b3 trades.db (fallback) ──────────────────

def _get_latest_price(ticker: str) -> dict:
    """Get the latest trade price from b3 trades.db."""
    try:
        import sqlite3
        from data_sources.b3.api.catalog import db_path as b3_db_path
        trades_db = b3_db_path("trades")
        if not trades_db.exists():
            return {"status": "not_synced",
                    "error": f"trades.db not found. Run data_source(domain='b3', sub_domain='api', mode='sync', params='{{\"table\":\"trades\"}}')."}
        conn = sqlite3.connect(f"file:{trades_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT RptDt, LastPric, OscnPctg, TradQty, NtlFinVol "
            "FROM trades WHERE TckrSymb=? ORDER BY RptDt DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if not row:
            return {"status": "not_found", "error": f"No trades found for {ticker} in trades.db"}
        return {
            "status": "ok",
            "date": row["RptDt"],
            "last_price": float(row["LastPric"]) if row["LastPric"] else None,
            "oscillation_pct": float(row["OscnPctg"]) if row["OscnPctg"] else None,
            "volume": float(row["NtlFinVol"]) if row["NtlFinVol"] else None,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Internal: get latest annual financials from DFP ──────────────────────────

def _get_latest_financials(ticker: str) -> dict:
    """Get latest annual financials from DFP."""
    try:
        conn = connect_dfp(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # [v1.0.6] auto_sync=True — if ticker not in bridge.db, auto-sync it
        # (fetches dividends + CAD lookup + upserts bridge). This makes the
        # valuation skill work for ANY ticker without pre-syncing the bridge.
        empresa_ids, company_name = resolve_company(conn, ticker, auto_sync=True)
        if not empresa_ids:
            return {"status": "not_found",
                    "error": f"Company '{ticker}' not found in DFP. "
                             f"Sync the bridge: data_source(domain='cvm', sub_domain='bridge', mode='sync', params='{{\"ticker\":\"{ticker}\"}}')"}

        codes = ["3.11", "2.03", "3.05", "6.01", "1.01.01", "2.01.04", "2.02.01", "7.08.04"]
        emp_ph = ",".join("?" * len(empresa_ids))
        code_ph = ",".join("?" * len(codes))

        year_row = conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=1
                ORDER BY data_fim_exerc DESC LIMIT 1""",
            (*empresa_ids, *codes),
        ).fetchone()

        if not year_row:
            return {"status": "not_found", "error": f"No annual data for '{ticker}'"}

        target_date = year_row["data_fim_exerc"]
        year = int(target_date[:4])

        rows = conn.execute(
            f"""SELECT codigo, valor, escala FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=1
                AND data_fim_exerc=?""",
            (*empresa_ids, *codes, target_date),
        ).fetchall()

        vals = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            vals[r["codigo"]] = float(r["valor"] or 0) * escala

        divida_bruta = None
        d_circ = vals.get("2.01.04")
        d_ncirc = vals.get("2.02.01")
        if d_circ is not None or d_ncirc is not None:
            divida_bruta = (d_circ or 0) + (d_ncirc or 0)

        return {
            "status": "ok",
            "ano": year,
            "company": company_name,
            "empresa_ids_count": len(empresa_ids),
            "rows_found": len(rows),
            "lucro_liquido": vals.get("3.11"),
            "patrimonio_liquido": vals.get("2.03"),
            "ebit": vals.get("3.05"),
            "fco": vals.get("6.01"),
            "caixa": vals.get("1.01.01"),
            "divida_bruta": divida_bruta,
            "proventos": vals.get("7.08.04"),
        }
    finally:
        conn.close()


# ── Internal: get shares outstanding from FRE ────────────────────────────────

def _get_shares_outstanding(ticker: str) -> dict:
    """Get total shares outstanding from FRE distribuicao_capital table."""
    try:
        conn = connect_fre(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        from data_sources.cvm._bridge import _resolve_via_bridge, _auto_sync_bridge
        cnpj, _ = _resolve_via_bridge(ticker)
        if not cnpj:
            # [v1.0.6] Auto-sync bridge for new tickers
            if _auto_sync_bridge(ticker):
                cnpj, _ = _resolve_via_bridge(ticker)
        if not cnpj:
            return {"status": "not_found", "error": f"Ticker '{ticker}' not in bridge.db"}

        # [v1.0.5] Try distribuicao_capital first, then capital_social, then investsite
        # Use REPLACE for CNPJ comparison (same fix as DFP — FRE may have formatted CNPJs)
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
            # Fallback: on + pn if total is missing
            if not total and (on_shares or pn_shares):
                total = (on_shares or 0) + (pn_shares or 0)

        # Fallback 1: try capital_social table
        if not total:
            try:
                row2 = conn.execute(
                    "SELECT * FROM capital_social "
                    "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '')=? "
                    "ORDER BY data_referencia DESC LIMIT 1",
                    (cnpj,),
                ).fetchone()
                if row2:
                    # capital_social has different column names
                    for key in ["qtd_total", "total_shares", "quantidade_total"]:
                        if key in row2.keys() and row2[key]:
                            total = int(row2[key])
                            break
                    if "data_referencia" in row2.keys():
                        data_ref = row2["data_referencia"] or data_ref
            except Exception:
                pass  # table might not exist

        conn.close()

        # Fallback 2: get shares from investsite (balanco_patrimonial section)
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
            return {"status": "not_found",
                    "error": f"No share data for {ticker} in fre.db or investsite. "
                             f"CNPJ={cnpj}. Check if FRE is synced."}

        return {
            "status": "ok",
            "total_shares": int(total) if total else None,
            "on_shares": int(on_shares) if on_shares else None,
            "pn_shares": int(pn_shares) if pn_shares else None,
            "data_referencia": data_ref,
            "source": "fre",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_div(a: float | None, b: float | None) -> float | None:
    """Safe division. Returns None if either is None or b is 0."""
    if a is None or b is None or b == 0:
        return None
    return a / b
