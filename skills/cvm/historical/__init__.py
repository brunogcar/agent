"""skills/cvm/historical/__init__.py -- Historical ratios skill manifest + router.

Auto-generates the MANIFEST modes from the metric registry. Adding a new
metric = drop a file in calculations/metrics/ + register_metric(). The
<metric>_history mode appears in the MANIFEST automatically. No edits to
this file.

Architecture:
  Engines (calculations/engines/) — one per raw quantity, auto-discovered:
    - price.py    — COTAHIST daily close
    - earnings.py — DFP + ITR TTM earnings derivation
    - shares.py   — FRE shares outstanding (+ investsite fallback)
    - pl.py       — DFP + ITR BPP 2.03 Patrimônio Líquido snapshot
  Metrics (calculations/metrics/) — one per ratio, auto-discovered +
  self-registered:
    - lpa.py      — LPA (earnings/shares) + P/L (price/LPA)
    - vpa.py      — VPA (pl/shares) + P/VPA (price/VPA)
    - (35+ other metrics: roe, roic, ev_ebitda, dpa, rps, margins, etc.)

Each metric produces BOTH a per-share value AND a price ratio. The per-share
value is useful on its own (e.g., backtest filters). The ratio tells you if
the stock is cheap vs history.

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create historical's MODES dict.
     _registry in turn auto-registers one <metric>_history mode per
     registered metric (via _auto_register_metric_history_modes).
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new explicit mode = drop a file in modes/ + register_mode().
Adding a new <metric>_history mode = register_metric() in calculations.
No edits to __init__.py or _registry.py in either case.

Example:
  skill(domain="cvm", sub_domain="historical", mode="lpa_history", params='{"company":"PETR4","months":60}')
  skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')
  skill(domain="cvm", sub_domain="historical", mode="summary",     params='{"company":"PETR4","metric":"vpa"}')
  skill(domain="cvm", sub_domain="historical", mode="dashboard",   params='{"company":"PETR4"}')
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.historical._registry import MODES  # noqa: F401

# Auto-discover all explicit mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

# [v2.0] Data sources this skill needs. The route() wrapper checks freshness
# before each dispatch and triggers force-sync if any source is stale.
REQUIRED_SOURCES = ["dfp", "itr", "cotahist", "bridge", "sgs"]

# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "historical",
    "description": (
        "Historical financial ratios over time. "
        "Each metric produces a per-share value (LPA, VPA) + a price ratio (P/L, P/VPA). "
        "<metric>_history: daily time series (auto-generated per metric). "
        "ratio_history: any metric over time. "
        "summary: current vs 1Y/3Y/5Y average + percentile. "
        "dashboard: multi-tab composition (Overview/Percentile Analysis/Trend/Ratio Grid)."
    ),
    "source":  "COTAHIST (price) + DFP/ITR (earnings TTM, PL snapshot) + FRE (shares)",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(MODES),
    "required_sources": REQUIRED_SOURCES,
}

# [v2.0] route() with sync guard.
route = make_route("sub_domain", "historical", MODES,
                   required_sources=REQUIRED_SOURCES)
