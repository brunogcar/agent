"""skills/cvm/comparison/__init__.py -- Comparison skill manifest + router.

Compares N tickers across the 3 CVM analytical dimensions (financials +
valuation + dividends) in one call. Calls the existing skills internally
(financials.summary, valuation.ratios, dividends.summary) per ticker and
merges into a side-by-side structure.

NO SYNC — read-only, like all CVM skills. No own database. Pure orchestration
over the existing skills.

Auto-discovery:
  1. Import _registry to ensure the MODES dict exists.
  2. Auto-discover all modes/*.py files via importlib.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes() turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.

Example:
  skill(domain="cvm", sub_domain="comparison", mode="side_by_side",
        params='{"tickers":["PETR4","VALE3","ITUB4"]}')
"""

from __future__ import annotations
import importlib
import inspect
from pathlib import Path

# Import _registry to ensure MODES dict exists.
from skills.cvm.comparison._registry import MODES, build_manifest_modes  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
# Each module's @register_mode decorator populates MODES.
_modes_dir = Path(__file__).parent / "modes"
for _py_file in sorted(_modes_dir.glob("*.py")):
    if _py_file.name == "__init__.py":
        continue
    _module_name = f"skills.cvm.comparison.modes.{_py_file.stem}"
    importlib.import_module(_module_name)


# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "comparison",
    "description": (
        "Compare N tickers across financials + valuation + dividends. "
        "side_by_side: 3 sections (valuation, financials, dividends), tickers as rows. "
        "summary: single quick-compare table (10 KPIs). "
        "growth: QoQ + YoY % change + TTM ratios. "
        "dashboard: multi-tab composition (Overview/Valuation/Financials/Dividends/Growth)."
    ),
    "source":  "calls financials + valuation + dividends skills internally",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(),
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch comparison mode call.

    Args:
        mode: Mode name ("side_by_side", "summary", "growth", "dashboard").
            Required — empty returns an error.
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
        return {"status": "error", "sub_domain": "comparison",
                "mode": mode, "error": str(e)}
