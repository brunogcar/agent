"""skills/cvm/backtest/__init__.py -- Backtest skill manifest + router.

Backtesting engine for CVM strategies. Uses calculations engines + metrics
for signal generation + return computation. Reuses the same engines/metrics
as the historical skill — no data duplication.

Example:
  skill(domain="cvm", sub_domain="backtest", mode="run",
        params='{"ticker":"PETR4","strategy":"value_pe"}')
  skill(domain="cvm", sub_domain="backtest", mode="strategies")
  skill(domain="cvm", sub_domain="backtest", mode="dashboard",
        params='{"ticker":"PETR4"}')

Auto-discovery (via skills._base):
  1. _registry.py calls make_registry() to create backtest's MODES dict.
  2. __init__.py calls auto_discover_modes(__name__) to import all modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes(MODES) turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.
"""

from __future__ import annotations

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.backtest._registry import MODES  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
auto_discover_modes(__name__)

# [v1.2] Data sources this skill needs. The route() wrapper checks freshness
# before each dispatch and triggers force-sync if any source is stale.
REQUIRED_SOURCES = ["cotahist", "bridge"]

# Build MANIFEST from the registered modes.
MANIFEST = {
    "sub_domain":  "backtest",
    "description": (
        "Backtesting engine. run: execute a strategy on a ticker over a date range. "
        "strategies: list available built-in strategies. "
        "results: analyze backtest results (CAGR, Sharpe, max drawdown). "
        "dashboard: multi-tab composition (Overview/Trades/Performance)."
    ),
    "source":  "COTAHIST (price) + calculations engines/metrics (signals)",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(MODES),
    "required_sources": REQUIRED_SOURCES,
}

# [v1.2] route() with sync guard.
route = make_route("sub_domain", "backtest", MODES,
                   required_sources=REQUIRED_SOURCES)
