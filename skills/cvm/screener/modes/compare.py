"""Mode: compare -- compare a ticker against its sector medians.

Resolves the ticker's sector from CAD (via bridge -> CNPJ -> CAD lookup ->
SETOR_ATIV), reuses sector() to get peers + medians, then builds a
per-metric comparison with "cheap"/"expensive"/"above"/"below" labels.

Registered as "compare" in skills.cvm.screener._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.screener._registry import register_mode
from skills.cvm.screener.helpers import _roe_from_ratios, _build_comparison


@register_mode(
    "compare",
    description=(
        "Compare a ticker against its sector medians. Resolves the ticker's "
        "sector, fetches all sector peers, computes medians, returns the "
        "ticker's values vs sector medians."
    ),
    include_in_all=False,
    params={
        "company": "str. B3 ticker (e.g. 'SUZB3'). Required.",
        "limit":   "int. Max peers to fetch for median. Default: 20.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="screener", mode="compare", params=\'{"company":"SUZB3"}\')',
    ],
)
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
    from skills.cvm.screener.modes.sector import sector
    sector_result = sector(setor=setor, limit=limit)
    if sector_result.get("status") != "ok":
        return sector_result

    peers = sector_result.get("peers", [])
    medians = sector_result.get("medians", {})

    # 3. Find this ticker in the peers list
    my_data = next((p for p in peers if p.get("ticker") == ticker), None)

    # 4. If not in peers (maybe valuation failed for this ticker), fetch separately
    if my_data is None:
        from skills.cvm.valuation.modes.ratios import ratios as val_ratios
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
                    # [v1.2] New metrics from calculations engines via valuation.ratios()
                    "roa": r.get("roa"),
                    "margem_liquida": r.get("margem_liquida"),
                    "divida_pl": r.get("divida_pl"),
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
