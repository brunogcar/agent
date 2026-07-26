"""skills/cvm/historical/_registry.py -- Central auto-discovery registry.

Single source of truth for engine + metric discovery in this skill. Lives at
the TOP LEVEL of the skill (not inside engines/ or metrics/) so it can
auto-discover BOTH subfolders.

This is the PATTERN TEMPLATE for other skills that need extensibility. Copy
this file + the engines/ and metrics/ folder structure. Do NOT create a
shared registry helper across skills — each skill has its own _registry.py.

ARCHITECTURE
------------
- Engines (engines/): one per raw quantity. Self-register via
  register_engine(EngineSpec(...)). Leaves — never import each other or metrics.
- Metrics (metrics/): one per ratio. Self-register via
  register_metric(MetricSpec(...)). Compose 2+ engines. Never query CVM/B3
  directly.

AUTO-DISCOVERY
--------------
At import time, this module:
  1. Globs engines/*.py and imports each (triggers register_engine calls)
  2. Globs metrics/*.py and imports each (triggers register_metric calls)

Adding a new engine = drop a file in engines/ + register_engine(). No edits
to __init__.py or _registry.py.
Adding a new metric = drop a file in metrics/ + register_metric(). The
<metric>_history mode, chart adapter, ratio_history dispatch, and summary
metric-awareness all auto-generate.

ENGINE SPEC
-----------
Each engine registers an EngineSpec with:
  - name:        engine name (file name without .py) — "price", "earnings", "shares", "pl"
  - quantity:    JSON key in periods entries — "close", "ttm", "shares", "pl"
  - at_fn:       fn(company, date) -> float | None
  - periods_fn:  fn(company) -> list[dict]
  - source:      human-readable data source — "COTAHIST", "DFP+ITR", etc.

METRIC SPEC
-----------
Each metric registers a MetricSpec with:
  - name:            canonical metric name — "lpa", "vpa", "dpa"
  - per_share_label: human label for per-share value — "LPA", "VPA", "DPA"
  - per_share_key:   JSON key in series entries — "lpa", "vpa", "dpa"
  - per_share_fn:    fn(company, date) -> per-share float | None
  - ratio_label:     human label for price ratio — "P/L", "P/VPA", "Div Yield"
  - ratio_key:       JSON key in series entries — "pe", "pvpa", "dy"
  - ratio_fn:        fn(company, date) -> ratio float | None
  - history_fn:      fn(company, date_from, date_to) -> list[dict]
  - engines:         list of engine names this metric composes
  - aliases:         alternative names for dispatch

Each metric produces BOTH a per-share value AND a price ratio. Some metrics
also produce bonus ratios (e.g., dpa produces DPA + DY + Payout).
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ── Engine spec ──────────────────────────────────────────────────────────────

@dataclass
class EngineSpec:
    """Specification for a historical engine.

    An engine fetches ONE raw quantity at any historical date from its data
    source(s). Engines are LEAVES — they never import each other or metrics.

    Attributes:
        name:        Engine name (file name without .py). "price", "earnings", etc.
        quantity:    JSON key in periods entries. "close", "ttm", "shares", "pl".
        at_fn:       fn(company, date) -> float | None. Value at most recent
                     data point <= date.
        periods_fn:  fn(company) -> list[dict]. All data points as
                     [{"date": "YYYY-MM-DD", "<quantity>": value}, ...] sorted
                     oldest-first.
        source:      Human-readable data source. "COTAHIST", "DFP+ITR", etc.
                     Used in docs + for backtest skill discovery.
        category:    Engine category for organizational grouping. One of:
                     - "market":  B3 market data (price, dividends)
                     - "shares":  shares outstanding (FRE/investsite)
                     - "dre":     DRE statement (earnings, revenue, ebit, etc.)
                     - "bpa":     BPA statement (assets)
                     - "bpp":     BPP statement (PL, debt)
                     - "dfc":     DFC statement (cash flow)
                     - "other":   anything else
                     Used by list_engines(category=...) for filtering.
                     When we reach 15+ engines, we may move to subfolders
                     (engines/dre/, engines/bpa/, etc.) — until then, the
                     category field gives organizational clarity without
                     breaking import paths.
    """
    name: str
    quantity: str
    at_fn: Callable
    periods_fn: Callable
    source: str
    category: str = "other"


# ── Metric spec ──────────────────────────────────────────────────────────────

@dataclass
class MetricSpec:
    """Specification for a historical metric.

    A metric can be one of three types:
      1. Per-share + price ratio (lpa, vpa, dpa, rps): produces a per-share
         value (LPA, VPA, DPA, RPS) AND a price ratio (P/L, P/VPA, Div Yield,
         PSR). Both per_share_* and ratio_* fields are set.
      2. Fundamental ratio (roe, roa, roic): produces only a ratio of two
         engine values (e.g., ROE = earnings / PL). No per-share value, no
         price. per_share_* fields are None.
      3. (Future) Per-share only: a per-share value without a price ratio.
         ratio_* fields would be None. Not used yet.

    For per-share + price ratio metrics, the history series includes both
    the per-share value and the ratio. For fundamental ratios, the series
    includes only the ratio (+ engine-specific fields).

    Some metrics also produce bonus ratios (e.g., dpa produces DPA + DY +
    Payout). The bonus ratios are added to the series entries by the metric's
    history_fn, but the primary ratio (ratio_key) is used for percentile +
    averages in summary().

    Attributes:
        name:            Canonical metric name (file name without .py).
        per_share_label: Human label for the per-share value (e.g., "LPA").
                         None for fundamental ratios (ROE, ROA).
        per_share_key:   JSON key in series entries (e.g., "lpa").
                         None for fundamental ratios.
        per_share_fn:    fn(company, date) -> per-share float | None.
                         None for fundamental ratios.
        ratio_label:     Human label for the ratio (e.g., "P/L", "ROE").
        ratio_key:       JSON key in series entries (e.g., "pe", "roe").
        ratio_fn:        fn(company, date) -> ratio float | None.
        history_fn:      fn(company, date_from, date_to) -> list[dict].
                         Each entry has: date, price (if applicable),
                         <per_share_key> (if applicable), <ratio_key>,
                         + engine-specific fields + bonus ratios.
        engines:         List of engine names this metric composes (for docs).
        aliases:         Alternative names for dispatch (e.g., ["pe", "pl"]).
    """
    name: str
    ratio_label: str
    ratio_key: str
    ratio_fn: Callable
    history_fn: Callable
    engines: list[str]
    per_share_label: str | None = None
    per_share_key: str | None = None
    per_share_fn: Callable | None = None
    aliases: list[str] = field(default_factory=list)


# ── Registries ───────────────────────────────────────────────────────────────

ENGINES: dict[str, EngineSpec] = {}
METRICS: dict[str, MetricSpec] = {}
_ALIASES: dict[str, str] = {}  # alias -> canonical metric name


def register_engine(spec: EngineSpec) -> EngineSpec:
    """Register an engine spec. Called at import time by each engine module.

    Raises ValueError if the name is already registered.
    """
    if spec.name in ENGINES:
        raise ValueError(f"Duplicate engine registration: '{spec.name}'")
    ENGINES[spec.name] = spec
    return spec


def register_metric(spec: MetricSpec) -> MetricSpec:
    """Register a metric spec. Called at import time by each metric module.

    Raises ValueError if the name or any alias is already registered.
    """
    if spec.name in METRICS:
        raise ValueError(f"Duplicate metric registration: '{spec.name}'")
    for alias in spec.aliases:
        if alias in _ALIASES:
            raise ValueError(
                f"Alias '{alias}' for metric '{spec.name}' "
                f"conflicts with existing alias for '{_ALIASES[alias]}'"
            )
    METRICS[spec.name] = spec
    for alias in spec.aliases:
        _ALIASES[alias] = spec.name
    return spec


# ── Resolution helpers ───────────────────────────────────────────────────────

def resolve_metric(name: str) -> MetricSpec:
    """Resolve a metric name or alias to its MetricSpec.

    Args:
        name: Metric name ("lpa", "vpa", "dpa") or alias ("pe", "pl", "dy").

    Raises:
        ValueError: If the name is not a registered metric or alias.
    """
    name = name.strip().lower()
    canonical = _ALIASES.get(name, name)
    if canonical not in METRICS:
        available = sorted(METRICS.keys())
        raise ValueError(
            f"Unknown metric '{name}'. Available: {available}"
        )
    return METRICS[canonical]


def list_engines(category: str | None = None) -> list[str]:
    """Return sorted list of engine names, optionally filtered by category.

    Args:
        category: If provided, only return engines with this category
                  (e.g., "dre", "bpa", "bpp", "market", "shares", "dfc").
                  If None (default), return all engines.
    """
    if category is None:
        return sorted(ENGINES.keys())
    return sorted(name for name, spec in ENGINES.items() if spec.category == category)


def list_engine_categories() -> list[str]:
    """Return sorted list of all engine categories currently in use."""
    return sorted(set(spec.category for spec in ENGINES.values()))


def list_metrics() -> list[str]:
    """Return sorted list of canonical metric names."""
    return sorted(METRICS.keys())


def list_all_metric_names() -> list[str]:
    """Return sorted list of all metric names (canonical + aliases)."""
    return sorted(set(list(METRICS.keys()) + list(_ALIASES.keys())))


# ── Auto-discovery ───────────────────────────────────────────────────────────
# Globs engines/*.py and metrics/*.py and imports each via importlib.
# This triggers register_engine() / register_metric() in each module.
# sorted() ensures deterministic import order across filesystems.

def _auto_discover() -> None:
    """Auto-discover and import all engine + metric modules.

    Called once at module load. Idempotent — uses a flag to avoid re-running
    on re-import (which can happen in test environments).
    """
    if getattr(_auto_discover, "_done", False):
        return
    _auto_discover._done = True

    base = Path(__file__).parent

    # Discover engines
    for py_file in sorted((base / "engines").glob("*.py")):
        if py_file.name != "__init__.py":
            module_name = f"skills.cvm.historical.engines.{py_file.stem}"
            importlib.import_module(module_name)

    # Discover metrics
    for py_file in sorted((base / "metrics").glob("*.py")):
        if py_file.name != "__init__.py":
            module_name = f"skills.cvm.historical.metrics.{py_file.stem}"
            importlib.import_module(module_name)


# Run auto-discovery at import time
_auto_discover()
