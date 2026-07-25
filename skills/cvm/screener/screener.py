"""skills/cvm/screener/screener.py -- Sector screener logic.

Lists companies in a sector + computes sector medians (P/L, ROE, EV/EBITDA)
so the LLM can ask "is SUZB3 cheap vs its sector?".

DATA FLOW
---------
  CAD.search(setor=...) -> list of companies (CNPJ, CD_CVM, names)
  For each company: bridge reverse-lookup (CD_CVM -> ticker) -> valuation.ratios
  Aggregate: sector medians + per-company table

NO SYNC — read-only. Calls CAD + bridge + valuation internally.
"""

from __future__ import annotations

from typing import Any
from statistics import median


# ── Mode: sector ─────────────────────────────────────────────────────────────

def sector(setor: str = "", limit: int = 20) -> dict:
    """List all active companies in a sector with valuation ratios + sector medians.

    Args:
        setor: Sector name fragment (e.g. "Papel e Celulose", "Energia").
               Case-insensitive partial match against CAD SETOR_ATIV.
        limit: Max companies to fetch + compute ratios for. Default: 20.
    """
    if not setor:
        return {"status": "error", "error": "setor is required"}

    # 1. Search CAD for companies in this sector
    from data_sources.cvm.cad.query_engine import search as cad_search
    cad_result = cad_search(setor=setor, active_only=True, limit=limit)
    if cad_result.get("status") != "ok":
        return {"status": "error", "error": f"CAD search failed: {cad_result.get('error','')}"}

    companies = cad_result.get("companies") or []
    if not companies:
        return {"status": "not_found",
                "error": f"No active companies found in sector '{setor}'"}

    # 2. For each company: resolve ticker via bridge reverse-lookup, get valuation
    from data_sources.cvm.bridge.query_engine import lookup as bridge_lookup
    from skills.cvm.valuation.valuation import ratios as val_ratios

    peers: list[dict] = []
    errors: list[str] = []

    for comp in companies:
        cd_cvm = comp.get("CD_CVM", "")
        cnpj = comp.get("CNPJ_CIA", "")
        name = comp.get("DENOM_COMERC") or comp.get("DENOM_SOCIAL") or ""

        # Bridge reverse-lookup: CD_CVM -> ticker
        ticker = None
        try:
            br = bridge_lookup(cd_cvm=cd_cvm)
            if br.get("status") == "ok":
                ticker = br.get("ticker")
        except Exception:
            pass

        if not ticker:
            # No ticker — skip (company exists but not publicly traded or not in bridge)
            continue

        # Get valuation ratios
        try:
            vr = val_ratios(company=ticker)
            if vr.get("status") == "ok":
                r = vr.get("ratios", {})
                peers.append({
                    "ticker": ticker,
                    "name": name,
                    "cnpj": cnpj,
                    "price": r.get("price"),
                    "market_cap": r.get("market_cap"),
                    "p_l": r.get("p_l"),
                    "p_vpa": r.get("p_vpa"),
                    "ev_ebitda": r.get("ev_ebitda"),
                    "roe": _roe_from_ratios(r),
                    "dividend_yield": r.get("dividend_yield"),
                })
            else:
                errors.append(f"{ticker}: valuation {vr.get('status')}")
        except Exception as e:
            errors.append(f"{ticker}: {e}")

    if not peers:
        return {"status": "not_found",
                "error": f"No peers with valuation data found in sector '{setor}'",
                "cad_companies_found": len(companies),
                "errors": errors}

    # 3. Compute sector medians
    medians = _compute_medians(peers)

    # 4. Sort by P/L (cheapest first) — None P/L goes last
    peers.sort(key=lambda p: (p.get("p_l") is None, p.get("p_l") or 0))

    return {
        "status": "ok",
        "setor": setor,
        "peer_count": len(peers),
        "medians": medians,
        "peers": peers,
        "errors": errors,
    }


# ── Mode: compare ────────────────────────────────────────────────────────────

def compare(company: str = "", limit: int = 20) -> dict:
    """Compare a ticker against its sector medians.

    Resolves the ticker's sector from CAD, fetches all sector peers, computes
    medians, returns the ticker's values vs the sector medians.

    Args:
        company: B3 ticker (e.g. "SUZB3"). Required.
        limit: Max peers to fetch for median computation. Default: 20.
    """
    if not company:
        return {"status": "error", "error": "company (ticker) is required"}

    ticker = company.strip().upper()

    # 1. Resolve ticker -> CNPJ -> sector via bridge + CAD
    from data_sources.cvm.bridge.query_engine import lookup as bridge_lookup
    from data_sources.cvm.cad.query_engine import lookup as cad_lookup

    br = bridge_lookup(ticker=ticker)
    if br.get("status") != "ok":
        return {"status": "not_found",
                "error": f"Ticker '{ticker}' not found in bridge: {br.get('error','')}"}

    cnpj = br.get("cnpj", "")
    cd_cvm = br.get("cd_cvm", "")
    company_name = br.get("denom_social") or br.get("trading_name") or ""

    # CAD lookup to get sector
    cr = cad_lookup(cnpj=cnpj)
    if cr.get("status") != "ok":
        cr = cad_lookup(cd_cvm=cd_cvm)
    if cr.get("status") != "ok":
        return {"status": "not_found",
                "error": f"Company '{ticker}' not found in CAD: {cr.get('error','')}"}

    setor = (cr.get("company") or {}).get("SETOR_ATIV", "")
    if not setor:
        return {"status": "not_found",
                "error": f"Company '{ticker}' has no SETOR_ATIV in CAD"}

    # 2. Get sector peers (reuse sector mode)
    sector_result = sector(setor=setor, limit=limit)
    if sector_result.get("status") != "ok":
        return sector_result

    peers = sector_result.get("peers", [])
    medians = sector_result.get("medians", {})

    # 3. Find this ticker in the peers list
    my_data = next((p for p in peers if p.get("ticker") == ticker), None)

    # 4. If not in peers (maybe valuation failed for this ticker), fetch separately
    if my_data is None:
        from skills.cvm.valuation.valuation import ratios as val_ratios
        try:
            vr = val_ratios(company=ticker)
            if vr.get("status") == "ok":
                r = vr.get("ratios", {})
                my_data = {
                    "ticker": ticker,
                    "name": company_name,
                    "price": r.get("price"),
                    "market_cap": r.get("market_cap"),
                    "p_l": r.get("p_l"),
                    "p_vpa": r.get("p_vpa"),
                    "ev_ebitda": r.get("ev_ebitda"),
                    "roe": _roe_from_ratios(r),
                    "dividend_yield": r.get("dividend_yield"),
                }
            else:
                my_data = {"ticker": ticker, "name": company_name,
                           "error": f"valuation: {vr.get('status')}"}
        except Exception as e:
            my_data = {"ticker": ticker, "name": company_name, "error": str(e)}

    # 5. Build comparison
    comparison = _build_comparison(my_data, medians)

    return {
        "status": "ok",
        "ticker": ticker,
        "name": company_name,
        "setor": setor,
        "peer_count": len(peers),
        "medians": medians,
        "my_data": my_data,
        "comparison": comparison,
        "peers": peers,
        "errors": sector_result.get("errors", []),
    }


# ── Internal: helpers ────────────────────────────────────────────────────────

def _roe_from_ratios(ratios: dict) -> float | None:
    """Extract ROE from valuation ratios (not directly in ratios — compute it)."""
    # valuation.ratios() doesn't return roe directly, but financials does.
    # ROE = lucro_liquido / patrimonio_liquido
    ll = ratios.get("lucro_liquido")
    pl = ratios.get("patrimonio_liquido")
    if ll is not None and pl is not None and pl > 0:
        return ll / pl
    return None


def _compute_medians(peers: list[dict]) -> dict:
    """Compute median P/L, P/VPA, EV/EBITDA, ROE, Div Yield from peers list."""
    def _median(key: str) -> float | None:
        vals = [p.get(key) for p in peers if p.get(key) is not None]
        return median(vals) if vals else None

    return {
        "p_l": _median("p_l"),
        "p_vpa": _median("p_vpa"),
        "ev_ebitda": _median("ev_ebitda"),
        "roe": _median("roe"),
        "dividend_yield": _median("dividend_yield"),
        "market_cap": _median("market_cap"),
    }


def _build_comparison(my_data: dict, medians: dict) -> dict:
    """Build a per-metric comparison: my value vs sector median + delta %."""
    metrics = ["p_l", "p_vpa", "ev_ebitda", "roe", "dividend_yield"]
    out = {}
    for m in metrics:
        my_val = my_data.get(m)
        med_val = medians.get(m)
        entry = {"my_value": my_val, "sector_median": med_val}
        if my_val is not None and med_val is not None and med_val != 0:
            entry["delta_pct"] = (my_val - med_val) / abs(med_val)
            # Interpretation: for P/L, P/VPA, EV/EBITDA — below median = "cheap"
            if m in ("p_l", "p_vpa", "ev_ebitda"):
                entry["vs_sector"] = "cheap" if my_val < med_val else "expensive"
            elif m in ("roe", "dividend_yield"):
                entry["vs_sector"] = "above" if my_val > med_val else "below"
        else:
            entry["delta_pct"] = None
            entry["vs_sector"] = "n/a"
        out[m] = entry
    return out
