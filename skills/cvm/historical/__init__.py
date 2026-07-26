"""skills/cvm/historical/__init__.py -- Historical ratios skill manifest + router.

Computes financial ratios (P/L, P/VPA, EV/EBITDA) over time by combining:
  - COTAHIST daily prices (2010-present)
  - DFP annual earnings + ITR quarterly cumulative earnings (TTM derivation)
  - FRE shares outstanding (annual)

The engines/ and metrics/ subpackages are designed to be importable standalone
for future use by a backtest skill.

Example:
  skill(domain="cvm", sub_domain="historical", mode="pe_history", params='{"company":"PETR4","months":60}')
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "historical",
    "description": (
        "Historical financial ratios over time. "
        "pe_history: daily P/L time series. "
        "ratio_history: any metric over time. "
        "summary: current vs 1Y/3Y/5Y average + percentile."
    ),
    "source":  "COTAHIST (price) + DFP/ITR (earnings TTM) + FRE (shares)",
    "storage": "read-only — no own database",
    "modes": {
        "pe_history": {
            "description": "Daily P/L time series for the last N months. Returns: date, price, ttm_earnings, shares, pe.",
            "include_in_all": False,
            "params": {
                "company": "str. Ticker. Required.",
                "months": "int. Number of months of history. Default: 60 (5 years).",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="historical", mode="pe_history", params=\'{"company":"PETR4","months":60}\')',
            ],
        },
        "ratio_history": {
            "description": "Any metric (pe, pvpa, ev_ebitda) over time. Currently only pe is implemented.",
            "include_in_all": False,
            "params": {
                "company": "str. Ticker. Required.",
                "metric": "str. Metric name: pe, pvpa, ev_ebitda. Default: pe.",
                "months": "int. Number of months. Default: 60.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="historical", mode="ratio_history", params=\'{"company":"PETR4","metric":"pe","months":120}\')',
            ],
        },
        "summary": {
            "description": "Current ratio vs 1Y/3Y/5Y average + min/max/percentile. Tells you if a stock is cheap vs its own history.",
            "include_in_all": True,
            "params": {
                "company": "str. Ticker. Required.",
                "metric": "str. Metric name. Default: pe.",
                "months": "int. History window for percentile. Default: 60.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="historical", mode="summary", params=\'{"company":"PETR4"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch historical mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.historical.historical import pe_history, ratio_history, summary

    dispatch = {
        "pe_history": pe_history,
        "ratio_history": ratio_history,
        "summary": summary,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "historical",
                "mode": mode, "error": str(e)}
