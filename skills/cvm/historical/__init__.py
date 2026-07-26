"""skills/cvm/historical/__init__.py -- Historical ratios skill manifest + router.

Auto-generates the MANIFEST modes from the metric registry. Adding a new
metric = drop a file in metrics/ + register_metric(). The <metric>_history
mode appears in the MANIFEST automatically. No edits to this file.

Architecture:
  Engines (engines/) — one per raw quantity, auto-discovered:
    - price.py    — COTAHIST daily close
    - earnings.py — DFP + ITR TTM earnings derivation
    - shares.py   — FRE shares outstanding (+ investsite fallback)
    - pl.py       — DFP + ITR BPP 2.03 Patrimônio Líquido snapshot
  Metrics (metrics/) — one per ratio, auto-discovered + self-registered:
    - lpa.py      — LPA (earnings/shares) + P/L (price/LPA)
    - vpa.py      — VPA (pl/shares) + P/VPA (price/VPA)

Each metric produces BOTH a per-share value AND a price ratio. The per-share
value is useful on its own (e.g., backtest filters). The ratio tells you if
the stock is cheap vs history.

Example:
  skill(domain="cvm", sub_domain="historical", mode="lpa_history", params='{"company":"PETR4","months":60}')
  skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')
  skill(domain="cvm", sub_domain="historical", mode="summary",     params='{"company":"PETR4","metric":"vpa"}')
"""

from __future__ import annotations
import inspect

# Importing _registry triggers auto-discovery of engines + metrics
from skills.cvm.historical._registry import METRICS, ENGINES, resolve_metric, list_metrics, list_engines


def _build_metric_modes() -> dict:
    """Auto-generate <metric>_history mode entries from the registry.

    Called once at module load. When a new metric is registered, its
    <metric>_history mode appears here automatically.
    """
    modes = {}
    for name in list_metrics():
        spec = METRICS[name]
        modes[f"{name}_history"] = {
            "description": (
                f"Daily {spec.per_share_label} + {spec.ratio_label} time series "
                f"for the last N months. Returns: date, price, "
                f"{', '.join(spec.engines + [spec.per_share_key, spec.ratio_key])}."
            ),
            "include_in_all": False,
            "params": {
                "company": "str. Ticker. Required.",
                "months": "int. Number of months of history. Default: 60 (5 years).",
            },
            "examples": [
                f'skill(domain="cvm", sub_domain="historical", mode="{name}_history", params=\'{{"company":"PETR4","months":60}}\')',
            ],
        }
    return modes


def _build_manifest() -> dict:
    """Build the skill MANIFEST with auto-generated metric modes."""
    modes = _build_metric_modes()

    # Generic modes (not tied to a specific metric)
    all_metric_names = ", ".join(list_metrics())
    modes["ratio_history"] = {
        "description": f"Any metric over time. Accepts: {all_metric_names} (+ aliases).",
        "include_in_all": False,
        "params": {
            "company": "str. Ticker. Required.",
            "metric": f"str. Metric name or alias ({all_metric_names}). Default: lpa.",
            "months": "int. Number of months. Default: 60.",
        },
        "examples": [
            'skill(domain="cvm", sub_domain="historical", mode="ratio_history", params=\'{"company":"PETR4","metric":"vpa","months":120}\')',
        ],
    }
    modes["summary"] = {
        "description": (
            "Current ratio vs 1Y/3Y/5Y average + min/max/percentile. "
            "Metric-aware: includes both per-share value and ratio in the result."
        ),
        "include_in_all": True,
        "params": {
            "company": "str. Ticker. Required.",
            "metric": f"str. Metric name or alias ({all_metric_names}). Default: lpa.",
            "months": "int. History window for percentile. Default: 60.",
        },
        "examples": [
            'skill(domain="cvm", sub_domain="historical", mode="summary", params=\'{"company":"PETR4"}\')',
            'skill(domain="cvm", sub_domain="historical", mode="summary", params=\'{"company":"PETR4","metric":"vpa"}\')',
        ],
    }
    return modes


MANIFEST = {
    "sub_domain":  "historical",
    "description": (
        "Historical financial ratios over time. "
        "Each metric produces a per-share value (LPA, VPA) + a price ratio (P/L, P/VPA). "
        "<metric>_history: daily time series (auto-generated per metric). "
        "ratio_history: any metric over time. "
        "summary: current vs 1Y/3Y/5Y average + percentile."
    ),
    "source":  "COTAHIST (price) + DFP/ITR (earnings TTM, PL snapshot) + FRE (shares)",
    "storage": "read-only — no own database",
    "modes": _build_manifest(),
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch historical mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.historical import historical

    # Build dispatch dict from the registry + generic modes
    dispatch = {}
    for name in list_metrics():
        dispatch[f"{name}_history"] = getattr(historical, f"{name}_history")
    dispatch["ratio_history"] = historical.ratio_history
    dispatch["summary"] = historical.summary

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "historical",
                "mode": mode, "error": str(e)}
