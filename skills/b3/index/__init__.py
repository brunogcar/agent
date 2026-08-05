"""skills/b3/index/__init__.py -- B3 index composition skill.

Combines B3 indexProxy data into multi-tab dashboards showing index
composition, top constituents, and comparison across indices.

Read-only - calls data_sources.b3.index query engines directly.

Modes:
  dashboard  -- multi-tab dashboard (Overview/IBOV/SMLL/BDRX/IFIX/IDIV)
  compare    -- compare index compositions
  ticker     -- find which indices a ticker belongs to
"""
from __future__ import annotations

from typing import Any

from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.b3.index._registry import MODES  # noqa: F401

auto_discover_modes(__name__)

REQUIRED_SOURCES = ["index"]

MANIFEST = {
    "sub_domain":  "index",
    "description": (
        "B3 index composition dashboard. "
        "dashboard: multi-tab (Overview/IBOV/SMLL/BDRX/IFIX/IDIV). "
        "compare: side-by-side index comparison. "
        "ticker: find which indices a ticker belongs to."
    ),
    "source":  "data_sources.b3.index",
    "storage": "read-only - no own database",
    "modes": build_manifest_modes(MODES),
    "required_sources": REQUIRED_SOURCES,
}

route = make_route("sub_domain", "index", MODES,
                   required_sources=REQUIRED_SOURCES)
