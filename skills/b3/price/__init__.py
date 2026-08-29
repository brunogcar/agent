"""skills/b3/price/__init__.py -- B3 price skill manifest + router."""
from __future__ import annotations
from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.b3.price._registry import MODES  # noqa: F401

auto_discover_modes(__name__)

# [v4] Removed "b3_dividends" from REQUIRED_SOURCES — per-ticker sync
REQUIRED_SOURCES = ["cotahist"]

MANIFEST = {
    "sub_domain":  "price",
    "description": (
        "B3 price analytics. dashboard: candlestick + MA + volume + returns + "
        "volatility + indicators + Fibonacci. quote: latest OHLCV snapshot."
    ),
    "source":  "data_sources.b3.cotahist + data_sources.b3.dividends",
    "storage": "read-only — no own database",
    "modes": build_manifest_modes(MODES),
    "required_sources": REQUIRED_SOURCES,
}

route = make_route("sub_domain", "price", MODES,
                   required_sources=REQUIRED_SOURCES)
