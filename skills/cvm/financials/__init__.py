"""skills/cvm/financials/__init__.py -- Financials skill manifest + router.

Combines DFP (annual) + ITR (quarterly cumulative) + DVA to produce
rapina-style financial summaries with standalone quarters + ratios.

Data sources used:
  - data_sources/cvm/dfp  (annual financial statements — meses=12)
  - data_sources/cvm/itr  (quarterly cumulative — meses=3/6/9)
  - data_sources/cvm/bridge (ticker → CNPJ → empresa_ids)

No sync — read-only over already-synced data.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create financials's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.financials._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "financials",
    "description": (
        "Financial statements + ratios. "
        "quarterly: standalone quarters derived from ITR cumulative + DFP (default). "
        "annual: annual summary from DFP. "
        "complete: full statements by grupo + key account codes. "
        "summary: combined latest annual + quarterly. "
        "dashboard: multi-tab composition (Overview/DRE/Balanço/DFC/Ratios)."
    ),
    "source":  "dfp.db (annual) + itr.db (quarterly cumulative) + dfp.db DVA (proventos)",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(MODES),
}

# Create the route() dispatcher via the shared factory.
route = make_route("sub_domain", "financials", MODES)
