"""metrics/_registry.py -- Auto-discovery registry for historical metrics.

A METRIC composes ENGINES. Each metric module self-registers here at import
time via the `register_metric()` function. The `metrics/__init__.py` auto-
discovers all `*.py` files in this directory (via glob + importlib), which
triggers each module's top-level `register_metric()` call.

WHY A REGISTRY?
---------------
Before v1.2, adding a new metric required editing:
  1. metrics/<name>.py        (the metric itself)
  2. metrics/__init__.py      (add to METRICS dict)
  3. historical.py            (add to _metric_dispatch if/elif)
  4. __init__.py              (add <name>_history mode to MANIFEST)

With the registry, adding a metric = drop a file in metrics/ + call
register_metric(). The MANIFEST modes, ratio_history() dispatch, and
summary() metric-awareness all auto-generate from the registry.

METRIC SPEC
-----------
Each metric registers a MetricSpec dataclass with:
  - name:           canonical metric name (e.g., "lpa", "vpa")
  - per_share_label: human label for the per-share value ("LPA", "VPA")
  - per_share_key:  JSON key in series entries ("lpa", "vpa")
  - per_share_fn:   function(company, date) -> per-share value
  - ratio_label:    human label for the price ratio ("P/L", "P/VPA")
  - ratio_key:      JSON key in series entries ("pe", "pvpa")
  - ratio_fn:       function(company, date) -> ratio value
  - history_fn:     function(company, date_from, date_to) -> list[dict]
  - engines:        list of engine names this metric composes (for docs)
  - aliases:        alternative names for ratio_history(metric=...) dispatch

EACH METRIC PRODUCES BOTH a per-share value AND a price ratio:
  - lpa metric: LPA (earnings/shares) + P/L (price/LPA)
  - vpa metric: VPA (pl/shares) + P/VPA (price/VPA)

The per-share value is useful on its own (e.g., backtest filters on LPA).
The ratio tells you if the stock is cheap vs history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class MetricSpec:
    """Specification for a historical metric.

    A metric produces BOTH a per-share value AND a price ratio. The per-share
    value comes from engines (e.g., earnings/shares = LPA). The ratio adds
    price (e.g., price/LPA = P/L). Both are exposed in the history series.

    Attributes:
        name:            Canonical metric name (file name without .py).
        per_share_label: Human label for the per-share value (e.g., "LPA").
        per_share_key:   JSON key in series entries (e.g., "lpa").
        per_share_fn:    fn(company, date) -> per-share float | None.
        ratio_label:     Human label for the price ratio (e.g., "P/L").
        ratio_key:       JSON key in series entries (e.g., "pe").
        ratio_fn:        fn(company, date) -> ratio float | None.
        history_fn:      fn(company, date_from, date_to) -> list[dict].
                         Each entry has: date, price, <per_share_key>,
                         <ratio_key>, + engine-specific fields.
        engines:         List of engine names this metric composes (for docs).
        aliases:         Alternative names for dispatch (e.g., ["pe", "pl"]).
    """
    name: str
    per_share_label: str
    per_share_key: str
    per_share_fn: Callable
    ratio_label: str
    ratio_key: str
    ratio_fn: Callable
    history_fn: Callable
    engines: list[str]
    aliases: list[str] = field(default_factory=list)


# ── Registry ─────────────────────────────────────────────────────────────────

METRICS: dict[str, MetricSpec] = {}
_ALIASES: dict[str, str] = {}  # alias → canonical name


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


def resolve_metric(name: str) -> MetricSpec:
    """Resolve a metric name or alias to its MetricSpec.

    Args:
        name: Metric name ("lpa", "vpa") or alias ("pe", "pl", "p/l", "pvpa").

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


def list_metrics() -> list[str]:
    """Return sorted list of canonical metric names."""
    return sorted(METRICS.keys())


def list_all_names() -> list[str]:
    """Return sorted list of all names (canonical + aliases)."""
    return sorted(set(list(METRICS.keys()) + list(_ALIASES.keys())))
