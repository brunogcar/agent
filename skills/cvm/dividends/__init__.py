"""skills/cvm/dividends/__init__.py -- Dividends skill manifest + router.

Combines B3 dividends (individual events) + DFP DVA (annual totals) +
CVM IPE (official filings).

Data sources used:
  - data_sources/b3/dividends  (cash_dividends table — individual events)
  - data_sources/cvm/dfp       (DVA 7.08.04.* — annual declared totals)
  - data_sources/cvm/ipe       (eventos table — keyword "dividendo")

No sync — read-only over already-synced data.

Auto-discovery:
  1. Import _registry to ensure the MODES dict exists.
  2. Auto-discover all modes/*.py files via importlib.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes() turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.
"""

from __future__ import annotations
import importlib
import inspect
from pathlib import Path

# Import _registry to ensure MODES dict exists.
from skills.cvm.dividends._registry import MODES, build_manifest_modes  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
# Each module's @register_mode decorator populates MODES.
_modes_dir = Path(__file__).parent / "modes"
for _py_file in sorted(_modes_dir.glob("*.py")):
    if _py_file.name == "__init__.py":
        continue
    _module_name = f"skills.cvm.dividends.modes.{_py_file.stem}"
    importlib.import_module(_module_name)


# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "dividends",
    "description": (
        "Dividend data combining 3 sources. "
        "history: individual events (B3). "
        "annual: declared totals (DFP DVA). "
        "payable: declared-but-unpaid (DFP BPP). "
        "announcements: official filings (IPE). "
        "summary: combined (default). "
        "dashboard: multi-tab composition (Overview/History/Annual)."
    ),
    "source":  "dividends.db (B3) + dfp.db (DVA 7.08.04.*) + ipe.db (filings)",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(),
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch dividends mode call.

    Args:
        mode: Mode name ("history", "annual", "payable", "announcements",
            "summary", "dashboard"). Required — empty returns an error.
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
        return {"status": "error", "sub_domain": "dividends",
                "mode": mode, "error": str(e)}
