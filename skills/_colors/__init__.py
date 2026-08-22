"""skills/_colors -- Modular color-scheme package for dashboard UIs.

Re-exports the per-domain coloring modules (price, dpa) so callers can do:

    from skills._colors import price_range_color, dpa_range_color

or import directly from the submodules:

    from skills._colors.price import price_range_color, ALL_RANGES as PRICE_RANGES
    from skills._colors.dpa   import dpa_range_color,   ALL_RANGES as DPA_RANGES

Each submodule owns its own range table + helpers; this __init__ just stitches
them together. Imports are wrapped in try/except so a broken / missing
submodule doesn't break the whole package import (e.g. during partial
installs or unit-test isolation).
"""
from __future__ import annotations

# Re-export the price color scheme (skills/_colors/price.py).
try:
    from skills._colors.price import (
        price_range_color,
        price_range_label,
        price_distribution,
        ALL_RANGES as PRICE_RANGES,
    )
except ImportError:  # pragma: no cover -- defensive: partial install / test isolation
    price_range_color = None  # type: ignore[assignment]
    price_range_label = None  # type: ignore[assignment]
    price_distribution = None  # type: ignore[assignment]
    PRICE_RANGES = []  # type: ignore[assignment]

# Re-export the DPA color scheme (skills/_colors/dpa.py).
try:
    from skills._colors.dpa import (
        dpa_range_color,
        dpa_range_label,
        dpa_distribution,
        ALL_RANGES as DPA_RANGES,
    )
except ImportError:  # pragma: no cover -- defensive: partial install / test isolation
    dpa_range_color = None  # type: ignore[assignment]
    dpa_range_label = None  # type: ignore[assignment]
    dpa_distribution = None  # type: ignore[assignment]
    DPA_RANGES = []  # type: ignore[assignment]


__all__ = [
    # price color scheme
    "price_range_color",
    "price_range_label",
    "price_distribution",
    "PRICE_RANGES",
    # dpa color scheme
    "dpa_range_color",
    "dpa_range_label",
    "dpa_distribution",
    "DPA_RANGES",
]
