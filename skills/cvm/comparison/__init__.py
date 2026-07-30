"""skills/cvm/comparison/__init__.py -- Comparison skill manifest + router.

Compares N tickers across the 3 CVM analytical dimensions (financials +
valuation + dividends) in one call. Calls the existing skills internally
(financials.summary, valuation.ratios, dividends.summary) per ticker and
merges into a side-by-side structure.

NO SYNC — read-only, like all CVM skills. No own database. Pure orchestration
over the existing skills.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create comparison's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.

Example:
  skill(domain="cvm", sub_domain="comparison", mode="side_by_side",
        params='{"tickers":["PETR4","VALE3","ITUB4"]}')
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.comparison._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

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
    "modes": build_manifest_modes(MODES),
}

# Create the route() dispatcher via the shared factory.
route = make_route("sub_domain", "comparison", MODES)
