"""skills/cvm/valuation/fetchers.py -- Price data fetching (brapi/investsite/b3).

Holds the internal price-fetching helpers consumed by modes/ratios.py. These
implement a 3-tier fallback chain for the current price (brapi -> investsite
-> b3 trades.db) that is NOT covered by the calculations price engine (which
is COTAHIST-only and used for historical daily prices).

[v2.0.0] KEPT from v1.0.14 -- the calculations price engine uses COTAHIST
only (historical daily prices). The 3-tier fallback here gets the CURRENT
price from brapi first, then investsite, then b3 trades.db. Will be merged
into the price engine in a future phase.

Functions:
  - _get_price               : 3-tier dispatcher (brapi -> investsite -> b3 trades).
  - _get_price_brapi         : brapi quote (also returns market_cap + pe_ratio).
  - _get_price_investsite     : investsite indicators (parses market_cap + pe + pvpa).
  - _get_latest_price         : b3 trades.db fallback (most recent trade).
"""
from __future__ import annotations

from datetime import datetime


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
