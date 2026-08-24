"""skills/_base/kpi.py — Shared KPI card builder.

Extracted from 7 DDM skills + 2 B3 skills that each had a near-identical
build_kpi_card function. The shape is universal: {label, value, raw,
subtitle} with optional formatted override + unit suffix.

[Phase 4 C1] Centralizes the KPI card dict shape so all dashboards are
consistent. A change to the KPI card layout (e.g. adding a tooltip) only
requires editing this one file.
"""
from __future__ import annotations


def build_kpi_card(
    label: str,
    value,
    *,
    subtitle: str = "",
    unit: str = "",
    formatted: str = "",
    format_fn=None,
) -> dict:
    """Build a KPI card dict.

    Args:
        label:     KPI label (e.g. "Ultima data").
        value:     Raw value (number / string).
        subtitle:  Optional subtitle / context.
        unit:      Optional unit hint (e.g. "mi", "%"). Not displayed
                   directly — used by the template for context.
        formatted: Pre-formatted display value (overrides format_fn).
                   Useful when value is already a display string like
                   "R$ 1.582,35 mi" or "19/08/2026".
        format_fn: Optional callable to format numeric values
                   (e.g. format_brl). Called as format_fn(value) when
                   value is a number and formatted is not set.

    Returns:
        {"label", "value", "raw", "subtitle", "unit"} dict.
    """
    if formatted:
        display = formatted
    elif isinstance(value, (int, float)) and format_fn is not None:
        display = format_fn(value)
    elif isinstance(value, (int, float)):
        display = str(value)
    else:
        display = str(value) if value is not None else "-"

    return {
        "label":    label,
        "value":    display,
        "raw":      value,
        "subtitle": subtitle,
        "unit":     unit,
    }
