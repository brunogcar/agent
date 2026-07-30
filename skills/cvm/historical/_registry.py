"""skills/cvm/historical/_registry.py — Mode registry + auto-discovery +
auto-generated <metric>_history modes.

Central dispatch table for historical modes. Each explicit mode lives in its
own file under modes/ and registers itself via @register_mode.

In addition to the explicit modes, this module AUTO-REGISTERS one
<metric>_history mode per registered metric in skills.cvm.calculations.
When a new metric is registered in calculations, its <metric>_history mode
appears here automatically — no edits to this file.

This mirrors the financials/_registry.py pattern (ModeSpec + register_mode +
build_manifest_modes) but adds the dynamic metric-history auto-registration
that's specific to historical.

Auto-discovery:
  1. __init__.py imports this module (ensures MODES dict exists +
     triggers _auto_register_metric_history_modes()).
  2. __init__.py auto-discovers modes/*.py via importlib.
  3. Each mode module's @register_mode decorator populates MODES.
  4. _auto_register_metric_history_modes() runs at the bottom of this module
     to add the dynamically-generated <metric>_history modes.

Adding a new explicit mode = drop a file in modes/ + register_mode().
Adding a new <metric>_history mode = register_metric() in calculations.
No edits to __init__.py or _registry.py in either case.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# Importing calculations._registry triggers auto-discovery of engines +
# metrics. This MUST happen before _auto_register_metric_history_modes()
# runs at the bottom of this module — otherwise METRICS would be empty.
from skills.cvm.calculations._registry import METRICS, list_metrics, resolve_metric

# Helpers provide the factory that builds each <metric>_history function.
from skills.cvm.historical.helpers import _make_metric_history_fn


@dataclass
class ModeSpec:
    """Specification for a historical mode.

    Attributes:
        name:           Mode name ("ratio_history", "summary", "dashboard",
                        or auto-generated "<metric>_history" like "lpa_history").
        fn:             Callable that implements the mode. fn(**kwargs) -> dict.
        description:    Human-readable description for manifest + help.
        params:         Dict of param_name -> description string.
        include_in_all: If True, this mode runs when sub_domain="all".
        examples:       List of example call strings.
    """
    name: str
    fn: Callable
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)
    include_in_all: bool = False
    examples: list[str] = field(default_factory=list)


# Global registry: mode_name -> ModeSpec
MODES: dict[str, ModeSpec] = {}


def register_mode(
    name: str,
    *,
    description: str = "",
    params: dict[str, str] | None = None,
    include_in_all: bool = False,
    examples: list[str] | None = None,
) -> Callable:
    """Decorator to register a historical mode.

    Usage in modes/summary.py:
        @register_mode("summary", description="...", params={...})
        def summary(company="", metric="lpa", months=60) -> dict:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        if name in MODES:
            raise ValueError(f"Duplicate mode registration: '{name}'")
        MODES[name] = ModeSpec(
            name=name,
            fn=fn,
            description=description,
            params=params or {},
            include_in_all=include_in_all,
            examples=examples or [],
        )
        return fn
    return decorator


def list_modes() -> list[str]:
    """Return sorted list of registered mode names."""
    return sorted(MODES.keys())


def get_mode(name: str) -> ModeSpec | None:
    """Get a ModeSpec by name, or None if not registered."""
    return MODES.get(name)


def build_manifest_modes() -> dict:
    """Build the MANIFEST['modes'] dict from registered ModeSpecs."""
    result = {}
    for name, spec in sorted(MODES.items()):
        result[name] = {
            "description": spec.description,
            "include_in_all": spec.include_in_all,
            "params": spec.params,
            "examples": spec.examples,
        }
    return result


# ── Auto-register <metric>_history modes ────────────────────────────────────
# For each metric in calculations.METRICS, register a <metric>_history mode
# that wraps _metric_history() with the canonical metric name. This is the
# mechanism behind lpa_history, vpa_history, dpa_history, etc. — adding a
# new metric in calculations automatically exposes its <metric>_history
# mode here without any edits.

def _auto_register_metric_history_modes() -> None:
    """Auto-register <metric>_history modes from the calculations registry.

    Idempotent — uses a flag to avoid re-running on re-import.
    """
    if getattr(_auto_register_metric_history_modes, "_done", False):
        return
    _auto_register_metric_history_modes._done = True

    for name in list_metrics():
        spec = METRICS[name]
        if spec.per_share_label:
            desc = (
                f"Daily {spec.per_share_label} + {spec.ratio_label} time series "
                f"for the last N months. Returns: date, price, "
                f"{', '.join(spec.engines + [spec.per_share_key, spec.ratio_key])}."
            )
        else:
            # Fundamental ratio — no per-share value, no price.
            desc = (
                f"Daily {spec.ratio_label} time series "
                f"for the last N months. Returns: date, "
                f"{', '.join(spec.engines + [spec.ratio_key])}."
            )
        params = {
            "company": "str. Ticker. Required.",
            "months": "int. Number of months of history. Default: 60 (5 years).",
        }
        examples = [
            f'skill(domain="cvm", sub_domain="historical", mode="{name}_history", '
            f'params=\'{{"company":"PETR4","months":60}}\')',
        ]
        fn = _make_metric_history_fn(name)
        # Use register_mode as a direct call rather than a decorator.
        register_mode(
            f"{name}_history",
            description=desc,
            params=params,
            include_in_all=False,
            examples=examples,
        )(fn)


_auto_register_metric_history_modes()
