"""skills/cvm/historical/__init__.py -- Historical ratios skill manifest + router.

Auto-generates the MANIFEST modes from the metric registry. Adding a new
metric = drop a file in calculations/metrics/ + register_metric(). The
<metric>_history mode appears in the MANIFEST automatically. No edits to
this file.

Architecture:
  Engines (calculations/engines/) — one per raw quantity, auto-discovered:
    - price.py    — COTAHIST daily close
    - earnings.py — DFP + ITR TTM earnings derivation
    - shares.py   — FRE shares outstanding (+ investsite fallback)
    - pl.py       — DFP + ITR BPP 2.03 Patrimônio Líquido snapshot
  Metrics (calculations/metrics/) — one per ratio, auto-discovered +
  self-registered:
    - lpa.py      — LPA (earnings/shares) + P/L (price/LPA)
    - vpa.py      — VPA (pl/shares) + P/VPA (price/VPA)
    - (35+ other metrics: roe, roic, ev_ebitda, dpa, rps, margins, etc.)

Each metric produces BOTH a per-share value AND a price ratio. The per-share
value is useful on its own (e.g., backtest filters). The ratio tells you if
the stock is cheap vs history.

Auto-discovery:
  1. Import _registry to ensure the MODES dict exists. _registry in turn
     auto-registers one <metric>_history mode per registered metric.
  2. Auto-discover all modes/*.py files via importlib.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes() turns the registry into MANIFEST["modes"].

Adding a new explicit mode = drop a file in modes/ + register_mode().
Adding a new <metric>_history mode = register_metric() in calculations.
No edits to __init__.py or _registry.py in either case.

Example:
  skill(domain="cvm", sub_domain="historical", mode="lpa_history", params='{"company":"PETR4","months":60}')
  skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')
  skill(domain="cvm", sub_domain="historical", mode="summary",     params='{"company":"PETR4","metric":"vpa"}')
  skill(domain="cvm", sub_domain="historical", mode="dashboard",   params='{"company":"PETR4"}')
"""

from __future__ import annotations
import importlib
import inspect
from pathlib import Path

# Import _registry to ensure MODES dict exists + auto-register <metric>_history
# modes from the calculations metric registry.
from skills.cvm.historical._registry import MODES, build_manifest_modes  # noqa: F401

# Auto-discover all explicit mode modules from modes/ subdirectory.
# Each module's @register_mode decorator populates MODES.
_modes_dir = Path(__file__).parent / "modes"
for _py_file in sorted(_modes_dir.glob("*.py")):
    if _py_file.name == "__init__.py":
        continue
    _module_name = f"skills.cvm.historical.modes.{_py_file.stem}"
    importlib.import_module(_module_name)


# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "historical",
    "description": (
        "Historical financial ratios over time. "
        "Each metric produces a per-share value (LPA, VPA) + a price ratio (P/L, P/VPA). "
        "<metric>_history: daily time series (auto-generated per metric). "
        "ratio_history: any metric over time. "
        "summary: current vs 1Y/3Y/5Y average + percentile. "
        "dashboard: multi-tab composition (Overview/Percentile Analysis/Trend)."
    ),
    "source":  "COTAHIST (price) + DFP/ITR (earnings TTM, PL snapshot) + FRE (shares)",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(),
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch historical mode call.

    Args:
        mode: Mode name ("ratio_history", "summary", "dashboard", or any
            "<metric>_history" like "lpa_history" / "vpa_history"). Required
            — empty returns an error.
        **kwargs: Forwarded to the mode function (filtered by the function's
            signature — unknown kwargs are silently dropped).

    Returns:
        Mode-specific dict on success, or ``{"status": "error", "error": ...}``
        on bad mode name or runtime failure.
    """
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MODES.keys())}"}
    if mode not in MODES:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MODES.keys())}"}

    spec = MODES[mode]
    fn = spec.fn
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "historical",
                "mode": mode, "error": str(e)}
