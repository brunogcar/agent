"""skills/cvm/dividends/__init__.py -- Dividends skill manifest + router.

Combines B3 dividends (individual events) + DFP DVA (annual totals) +
CVM IPE (official filings).

Data sources used:
  - data_sources/b3/dividends  (cash_dividends table — individual events)
  - data_sources/cvm/dfp       (DVA 7.08.04.* — annual declared totals)
  - data_sources/cvm/ipe       (eventos table — keyword "dividendo")

No sync — read-only over already-synced data.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create dividends's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.dividends._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

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
    "modes": build_manifest_modes(MODES),
}

# Create the route() dispatcher via the shared factory.
route = make_route("sub_domain", "dividends", MODES)
