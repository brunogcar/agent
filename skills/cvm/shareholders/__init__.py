"""skills/cvm/shareholders/__init__.py -- Shareholders skill manifest + router.

Combines FRE (named shareholders, free float) + DFP (equity structure in BRL).
Read-only — no sync. Calls data_sources.cvm.fre + data_sources.cvm.dfp directly.

Data sources used:
  - data_sources/cvm/fre  (posicao_acionaria, distribuicao_capital)
  - data_sources/cvm/dfp  (BPP 2.03.* Patrimônio Líquido)

No sync — read-only over already-synced data.

Auto-discovery:
  1. Import _registry to ensure the MODES dict exists.
  2. Auto-discover all modes/*.py files via importlib.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes() turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.

Example:
  skill(domain="cvm", sub_domain="shareholders", mode="summary", params='{"company":"PETR4"}')
"""

from __future__ import annotations
import importlib
import inspect
from pathlib import Path

# Import _registry to ensure MODES dict exists.
from skills.cvm.shareholders._registry import MODES, build_manifest_modes  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
# Each module's @register_mode decorator populates MODES.
_modes_dir = Path(__file__).parent / "modes"
for _py_file in sorted(_modes_dir.glob("*.py")):
    if _py_file.name == "__init__.py":
        continue
    _module_name = f"skills.cvm.shareholders.modes.{_py_file.stem}"
    importlib.import_module(_module_name)


# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "shareholders",
    "description": (
        "Shareholder + equity structure. "
        "Named shareholders (FRE) + free float (FRE) + equity breakdown in BRL (DFP BPP). "
        "Accepts B3 ticker (via bridge), name, or CNPJ. "
        "dashboard: multi-tab composition (Overview/Top Shareholders/Free Float/Equity Structure)."
    ),
    "source":  "fre.db (posicao_acionaria, distribuicao_capital) + dfp.db (BPP 2.03.*)",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(),
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch shareholders mode call.

    Args:
        mode: Mode name ("shareholders", "free_float", "equity_structure",
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
        return {"status": "error", "sub_domain": "shareholders",
                "mode": mode, "error": str(e)}
