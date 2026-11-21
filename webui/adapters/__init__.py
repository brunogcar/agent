"""webui/adapters/ — section payload contract + subtab adapter registry.

[v1.7] Preparation release for the v1.8 feature wave (Opções, Histórico,
Macro, …): the ad-hoc "service method → section dicts → generic client
renderer" pattern used by Valuation (v1.4) and Proventos (v1.6) becomes
an explicit contract with a registry and a generic dispatch endpoint.

  contract.py — payload/section shapes + builders + validation
  registry.py — "<family>:<sub>" registry, memoized service singletons,
                dispatch() with error containment + contract checks

Adding a v1.8 tab:
  1. service method → contract payload (use contract.py builders),
  2. register("options:overview", …) in registry.py,
  3. tab shell partial + client loader →
     GET /api/webui/company/{ticker}/sections/options:overview.
"""
from webui.adapters.contract import (
    SECTION_TYPES,
    chart_section,
    error_payload,
    heatmap_section,
    kpi,
    ratio_grid_section,
    table_section,
    two_column_section,
    validate_payload,
    validate_section,
)
from webui.adapters.registry import (
    adapter_keys,
    adapters_info,
    dispatch,
    has,
    register,
    service,
)

__all__ = [
    "SECTION_TYPES",
    "adapter_keys", "adapters_info",
    "chart_section", "dispatch",
    "error_payload",
    "heatmap_section", "has",
    "kpi",
    "ratio_grid_section", "register",
    "service",
    "table_section", "two_column_section",
    "validate_payload", "validate_section",
]
