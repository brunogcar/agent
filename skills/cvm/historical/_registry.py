"""skills/cvm/historical/_registry.py — Mode registry + auto-generated
<metric>_history modes for the historical skill.

Delegates to skills._base for the shared ModeSpec + register_mode +
build_manifest_modes infrastructure. This file exists to give historical
its own isolated MODES dict + to provide a stable import path for mode files:
    from skills.cvm.historical._registry import register_mode

In addition to the explicit modes (auto-discovered from modes/*.py by
__init__.py), this module AUTO-REGISTERS one <metric>_history mode per
registered metric in skills.cvm.calculations. When a new metric is registered
in calculations, its <metric>_history mode appears here automatically — no
edits to this file.

Auto-discovery flow:
  1. __init__.py imports this module (ensures MODES dict exists + triggers
     _auto_register_metric_history_modes()).
  2. __init__.py calls auto_discover_modes(__name__) to import modes/*.py.
  3. Each mode module's @register_mode decorator populates MODES.
  4. _auto_register_metric_history_modes() runs at the bottom of this module
     to add the dynamically-generated <metric>_history modes.

Adding a new explicit mode = drop a file in modes/ + register_mode().
Adding a new <metric>_history mode = register_metric() in calculations.
No edits to __init__.py or _registry.py in either case.
"""
from __future__ import annotations

# Importing calculations._registry triggers auto-discovery of engines +
# metrics. This MUST happen before _auto_register_metric_history_modes()
# runs at the bottom of this module — otherwise METRICS would be empty.
from skills.cvm.calculations._registry import METRICS, list_metrics, resolve_metric

# Helpers provide the factory that builds each <metric>_history function.
from skills.cvm.historical.helpers import _make_metric_history_fn

# Shared infrastructure: per-skill MODES dict + register_mode decorator +
# manifest/list/get accessors. Each skill must call make_registry() once to
# get its own isolated MODES dict (prevents cross-skill mode name pollution).
from skills._base import make_registry, build_manifest_modes, list_modes, get_mode

# Create historical's own isolated MODES dict + register_mode decorator.
MODES, register_mode = make_registry()


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
        mode_name = f"{name}_history"
        # Collision guard: skip if a mode with this name is already registered
        # (e.g., an explicit mode file in modes/ that happens to share the name).
        if mode_name in MODES:
            continue
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
            mode_name,
            description=desc,
            params=params,
            include_in_all=False,
            examples=examples,
        )(fn)


_auto_register_metric_history_modes()
