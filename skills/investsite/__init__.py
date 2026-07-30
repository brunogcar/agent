"""skills/investsite/__init__.py -- Investsite skill manifest + router.

Fetches financial data from investsite.com.br (per-ticker pages).

Unlike CVM/B3 skills which read from local databases, this skill fetches
live data from the web. No sync, no local DB — each call hits the site.

6 modes:
  indicators (default) — main page: 10 tables (prices, DRE, returns, balance, cashflow)
  statements          — full financial statement (BPA/BPP/DRE/DFC/DVA) with % total
  events              — periodic info by category with CVM PDF links
  summary             — combined: key indicators + latest events
  listing             — list available event categories
  dashboard           — multi-tab composition (Overview/Key Indicators/Latest Events)

[v1.1] Modular split: investsite.py monolith replaced by auto-discovery of
modes/*.py files via importlib (same pattern as governance/screener/
shareholders/insider/historical). fetcher.py + parsers.py are KEPT as
separate modules — only investsite.py was split. The MANIFEST keeps
"domain" (not "sub_domain") because investsite is a TOP-LEVEL flat domain,
not under cvm/. route() signature stays route(sub_domain="", mode="",
**kwargs) — the sub_domain param is accepted for dispatcher compatibility
but ignored.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create investsite's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.investsite._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

# Build MANIFEST from the registered modes.
MANIFEST = {
    "domain":       "investsite",
    "description":  (
        "Financial data from investsite.com.br (live web scraping). "
        "Per-ticker indicators, full statements, periodic events with CVM links. "
        "No local DB — fetches live each call. "
        "dashboard: multi-tab composition (Overview/Key Indicators/Latest Events)."
    ),
    "has_sub_domains": False,
    "source":  "investsite.com.br (live HTTP)",
    "storage": "in-memory cache only (1h TTL)",
    "modes": build_manifest_modes(MODES),
}

# Create the route() dispatcher via the shared factory. accept_sub_domain=True
# so route() accepts (and ignores) a sub_domain param for dispatcher compat.
route = make_route("domain", "investsite", MODES, accept_sub_domain=True)
