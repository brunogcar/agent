"""skills/cvm/insider/__init__.py -- Insider trading skill manifest + router.

Combines VLMO data (insider buy/sell disclosures) with bridge resolution.
Read-only — no sync. Calls data_sources.cvm.vlmo.query_engine directly.

Data sources used:
  - data_sources/cvm/vlmo  (VLMO — Valores Mobiliários)

No sync — read-only over already-synced data.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create insider's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.

Example:
  skill(domain="cvm", sub_domain="insider", mode="history", params='{"company":"PETR4"}')
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.insider._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

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
    "modes": build_manifest_modes(MODES),
    "required_sources": ["vlmo", "bridge"],
}

# [v2.1] Sync guard — insider needs VLMO + bridge for ticker resolution.
REQUIRED_SOURCES = ["vlmo", "bridge"]

# Create the route() dispatcher via the shared factory.
route = make_route("sub_domain", "insider", MODES,
                   required_sources=REQUIRED_SOURCES)
