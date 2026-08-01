"""Mode: sector -- list all active companies in a sector with valuation ratios.

Wraps CAD search + bridge reverse-lookup + valuation.ratios + financials.annual
to build a peer table with sector medians (P/L, P/VPA, EV/EBITDA, ROE,
Div Yield + v1.2/v1.4 calculations metrics).

Registered as "sector" in skills.cvm.screener._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.screener._registry import register_mode
from skills.cvm.screener.helpers import (
    _roe_from_ratios,
    _pct_change,
    _compute_medians,
)


@register_mode(
    "sector",
    description=(
        "List all active companies in a sector with their valuation ratios. "
        "Returns sector medians for P/L, ROE, EV/EBITDA."
    ),
    include_in_all=True,
    params={
        "setor":  "str. Sector name fragment (e.g. 'Papel', 'Energia', 'Bancos'). Required.",
        "limit":  "int. Max companies to fetch. Default: 20.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="screener", mode="sector", params=\'{"setor":"Papel e Celulose"}\')',
    ],
)
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

    # 2. For each company: resolve ticker via bridge reverse-lookup, get valuation + financials
    from data_sources.cvm.bridge.query_engine import lookup as bridge_lookup
    from skills.cvm.valuation.modes.ratios import ratios as val_ratios
    from skills.cvm.financials.modes.annual import annual as fin_annual
    from skills._base import engine_cache_scope

    peers: list[dict] = []
    errors: list[str] = []
    seen_cnpjs: set[str] = set()  # deduplicate by CNPJ (PETR3/PETR4 share CNPJ)
    total = min(len(companies), limit)

    print(f"[screener] Fetching ratios for {total} sector peers (with F7 cache)...", flush=True)

    # [v1.3 speed fix] Wrap the entire peer loop in engine_cache_scope so
    # shared engines (earnings, pl, shares, etc.) are cached across peers.
    # Without this, each peer's val_ratios() call re-queries DFP/ITR/FRE
    # from scratch — but many peers share the same fiscal year data.
    with engine_cache_scope() as cache:
        for i, comp in enumerate(companies):
            if len(peers) >= limit:
                break

            cd_cvm = comp.get("CD_CVM", "")
            cnpj = comp.get("CNPJ_CIA", "")
            name = comp.get("DENOM_COMERC") or comp.get("DENOM_SOCIAL") or ""

            # Deduplicate by CNPJ (PETR3 + PETR4 share the same CNPJ → same company)
            if cnpj and cnpj in seen_cnpjs:
                continue
            if cnpj:
                seen_cnpjs.add(cnpj)

            # Bridge reverse-lookup: CD_CVM -> ticker
            ticker = None
            try:
                br = bridge_lookup(cd_cvm=cd_cvm)
                if br.get("status") == "ok":
                    ticker = br.get("ticker")
            except Exception:
                pass

            if not ticker:
                continue

            print(f"[screener]   {len(peers)+1}/{limit}: {ticker}...", flush=True, end="")

            # Get valuation ratios (best-effort)
            peer: dict = {"ticker": ticker, "name": name, "cnpj": cnpj}
            try:
                vr = val_ratios(company=ticker)
                if vr.get("status") == "ok":
                    r = vr.get("ratios", {})
                    peer.update({
                        "price": r.get("price"),
                        "market_cap": r.get("market_cap"),
                        "p_l": r.get("p_l"),
                        "p_vpa": r.get("p_vpa"),
                        "ev_ebitda": r.get("ev_ebitda"),
                        "roe": _roe_from_ratios(r),
                        "dividend_yield": r.get("dividend_yield"),
                        # [v1.2] New metrics from calculations engines via valuation.ratios()
                        "roa": r.get("roa"),
                        "margem_liquida": r.get("margem_liquida"),
                        "divida_pl": r.get("divida_pl"),
                        # [v1.4] New v1.3 metrics — liquidity, cash flow, efficiency
                        "quick_ratio": r.get("quick_ratio"),
                        "cash_ratio": r.get("cash_ratio"),
                        "ocf_margin": r.get("ocf_margin"),
                        "fcf_margin": r.get("fcf_margin"),
                        "interest_coverage": r.get("interest_coverage"),
                        "cash_flow_to_debt": r.get("cash_flow_to_debt"),
                        "ev_sales": r.get("ev_sales"),
                        "ev_fcf": r.get("ev_fcf"),
                        "p_tangible_book": r.get("p_tangible_book"),
                    })
                else:
                    errors.append(f"{ticker}: valuation {vr.get('status')}")
            except Exception as e:
                errors.append(f"{ticker}: valuation {e}")

            # [v1.1] Get financials (best-effort) — revenue, EBITDA, margins, growth
            try:
                fr = fin_annual(company=ticker, periods=2)
                if fr.get("status") == "ok" and fr.get("periods"):
                    periods = fr["periods"]
                    latest = periods[0]
                    m = latest.get("metrics", {}) or {}
                    ratios = latest.get("ratios", {}) or {}
                    peer.update({
                        "receita_liquida": m.get("receita_liquida"),
                        "ebitda": m.get("ebitda"),
                        "lucro_liquido": m.get("lucro_liquido"),
                        "marg_ebitda": ratios.get("marg_ebitda"),
                        "marg_liquida": ratios.get("marg_liquida"),
                        "payout": ratios.get("payout"),
                    })
                    # Revenue growth: latest vs prior year (if 2+ periods)
                    if len(periods) >= 2:
                        prior_rev = (periods[1].get("metrics") or {}).get("receita_liquida")
                        curr_rev = m.get("receita_liquida")
                        peer["receita_growth"] = _pct_change(curr_rev, prior_rev)
                    else:
                        peer["receita_growth"] = None
                else:
                    errors.append(f"{ticker}: financials {fr.get('status')}")
            except Exception as e:
                errors.append(f"{ticker}: financials {e}")

            # [v1.2] Get listing segment from Fca (Novo Mercado, Nível 1, etc.)
            try:
                from data_sources.cvm._bridge import _resolve_via_fca_segmento
                peer["segmento"] = _resolve_via_fca_segmento(ticker) or ""
            except Exception:
                peer["segmento"] = ""

            peers.append(peer)
            print(" done.", flush=True)

        stats = cache.stats
        print(f"[screener] F7 cache: {stats['hits']} hits, {stats['misses']} misses.", flush=True)

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
