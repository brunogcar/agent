"""skills/cvm/comparison/__init__.py -- Comparison skill manifest + router.

Compares N tickers across the 3 CVM analytical dimensions (financials +
valuation + dividends) in one call. Calls the existing skills internally
(financials.summary, valuation.ratios, dividends.summary) per ticker and
merges into a side-by-side structure.

NO SYNC — read-only, like all CVM skills. No own database. Pure orchestration
over the existing skills.

Example:
  skill(domain="cvm", sub_domain="comparison", mode="side_by_side",
        params='{"tickers":["PETR4","VALE3","ITUB4"]}')
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "comparison",
    "description": (
        "Compare N tickers across financials + valuation + dividends. "
        "side_by_side: 3 sections (valuation, financials, dividends), tickers as rows. "
        "summary: single quick-compare table (10 KPIs)."
    ),
    "source":  "calls financials + valuation + dividends skills internally",
    "storage": "read-only — no own database",
    "modes": {
        "side_by_side": {
            "description": "3 sections — Valuation Ratios, Financial Metrics (latest annual), Dividend Metrics. Each section: rows = tickers, columns = metrics.",
            "include_in_all": False,
            "params": {
                "tickers":     "list[str]. B3 tickers, e.g. [\"PETR4\",\"VALE3\"]. Required (min 2).",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="comparison", mode="side_by_side", params=\'{"tickers":["PETR4","VALE3","ITUB4"]}\')',
                'skill(domain="cvm", sub_domain="comparison", mode="side_by_side", params=\'{"tickers":["SUZB3","KLBN11"]}\')',
            ],
        },
        "summary": {
            "description": "Single quick-compare table: 1 row per ticker, ~10 KPI columns (Preço, Market Cap, P/L, P/VPA, EV/EBITDA, ROE, Div Yield, Receita, EBITDA, Lucro Líquido).",
            "include_in_all": True,
            "params": {
                "tickers":     "list[str]. Required (min 2).",
                "consolidado": "int. Default: 1.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="comparison", mode="summary", params=\'{"tickers":["SUZB3","KLBN11"]}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch comparison mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.comparison.comparison import side_by_side, summary

    dispatch = {
        "side_by_side": side_by_side,
        "summary":      summary,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "comparison",
                "mode": mode, "error": str(e)}
