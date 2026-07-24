"""skills/cvm/valuation/__init__.py -- Valuation skill manifest + router.

Combines b3 price data + CVM DFP financials + FRE shares to compute
valuation ratios: P/L, P/VPA, EV, P/EBIT, P/FCO, Dividend Yield, Market Cap.

Data sources used:
  - data_sources/b3/api (trades.db — latest price)
  - data_sources/cvm/dfp (dfp.db — annual financials)
  - data_sources/cvm/fre (fre.db — shares outstanding)
  - data_sources/cvm/bridge (ticker → CNPJ → empresa_ids)

Uses core/br_validator for parse_escala, validate_ticker.

No sync — read-only over already-synced data.
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "valuation",
    "description": (
        "Valuation ratios (P/L, P/VPA, EV, Dividend Yield, P/EBIT, P/FCO) "
        "combining b3 price + CVM financials + FRE shares. "
        "The investsite goldmine — computed from local data."
    ),
    "source":  "b3 trades.db + cvm dfp.db + cvm fre.db + bridge.db",
    "storage": "read-only — no own database",
    "modes": {
        "ratios": {
            "description": "Compute all valuation ratios (P/L, P/VPA, EV, P/EBIT, P/FCO, Div Yield, Market Cap).",
            "include_in_all": True,
            "params": {
                "company": "str. B3 ticker (PETR4). Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="valuation", mode="ratios", params=\'{"company":"PETR4"}\')',
            ],
        },
        "summary": {
            "description": "Ratios + data source availability (which DBs are synced).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="valuation", mode="summary", params=\'{"company":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch valuation mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.valuation.valuation import ratios, summary

    dispatch = {
        "ratios": ratios,
        "summary": summary,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "valuation",
                "mode": mode, "error": str(e)}
