"""skills/cvm/insider/__init__.py -- Insider trading skill manifest + router.

Combines VLMO data (insider buy/sell disclosures) with bridge resolution.
Read-only — no sync. Calls data_sources.cvm.vlmo.query_engine directly.

Data sources used:
  - data_sources/cvm/vlmo  (VLMO — Valores Mobiliários)

No sync — read-only over already-synced data.

Auto-discovery:
  1. Import _registry to ensure the MODES dict exists.
  2. Auto-discover all modes/*.py files via importlib.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes() turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.

Example:
  skill(domain="cvm", sub_domain="insider", mode="history", params='{"company":"PETR4"}')
"""

from __future__ import annotations
import importlib
import inspect
from pathlib import Path

# Import _registry to ensure MODES dict exists.
from skills.cvm.insider._registry import MODES, build_manifest_modes  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
# Each module's @register_mode decorator populates MODES.
_modes_dir = Path(__file__).parent / "modes"
for _py_file in sorted(_modes_dir.glob("*.py")):
    if _py_file.name == "__init__.py":
        continue
    _module_name = f"skills.cvm.insider.modes.{_py_file.stem}"
    importlib.import_module(_module_name)


# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "insider",
    "description": (
        "Insider trading analysis from VLMO disclosures. "
        "history: recent insider transactions. "
        "by_role: grouped by role (director, officer, etc.). "
        "summary: net buy/sell per month. "
        "dashboard: multi-tab composition (Overview/Recent Transactions/By Role/Monthly Net). "
        "all: combined report."
    ),
    "source":  "vlmo.db (VLMO — Valores Mobiliários)",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(),
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch insider mode call.

    Args:
        mode: Mode name ("history", "by_role", "summary",
            "dashboard"). Required — empty returns an error.
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
        return {"status": "error", "sub_domain": "insider",
                "mode": mode, "error": str(e)}
