"""skills/cvm/shareholders/__init__.py -- Shareholders skill manifest + router.

Combines FRE (named shareholders, free float) + DFP (equity structure in BRL).
Read-only — no sync. Calls data_sources.cvm.fre + data_sources.cvm.dfp directly.

Data sources used:
  - data_sources/cvm/fre  (posicao_acionaria, distribuicao_capital)
  - data_sources/cvm/dfp  (BPP 2.03.* Patrimônio Líquido)

No sync — read-only over already-synced data.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create shareholders's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.

Example:
  skill(domain="cvm", sub_domain="shareholders", mode="summary", params='{"company":"PETR4"}')
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.shareholders._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

# [v1.2] Data sources this skill needs. The route() wrapper checks freshness
# before each dispatch and triggers force-sync if any source is stale.
REQUIRED_SOURCES = ["fre", "dfp", "bridge"]

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
    "modes": build_manifest_modes(MODES),
    "required_sources": REQUIRED_SOURCES,
}

# [v1.2] route() with sync guard.
route = make_route("sub_domain", "shareholders", MODES,
                   required_sources=REQUIRED_SOURCES)
