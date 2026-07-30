"""skills/cvm/screener/__init__.py -- Sector screener skill manifest + router.

Lists companies in a sector and computes sector medians (P/L, ROE, EV/EBITDA)
so the LLM can ask "is SUZB3 cheap vs its sector?".

NO SYNC — read-only, like all CVM skills. Calls CAD + bridge + valuation
internally.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create screener's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.

Example:
  skill(domain="cvm", sub_domain="screener", mode="sector",
        params='{"setor":"Papel e Celulose"}')
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.screener._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "screener",
    "description": (
        "Sector screener. List companies in a sector + compute median P/L, ROE, "
        "EV/EBITDA. compare: is a ticker cheap vs its sector? "
        "dashboard: multi-tab composition (Overview/Peers/Comparison)."
    ),
    "source":  "calls CAD + bridge + valuation skills internally",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(MODES),
}

# Create the route() dispatcher via the shared factory.
route = make_route("sub_domain", "screener", MODES)
