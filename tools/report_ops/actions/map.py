"""Map action handler — builds interactive Leaflet.js maps.

Lazy-imports the heavy maps builder to keep MCP startup fast.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops._registry import register_action


@register_action(
    "report",
    "map",
    help_text="""Build an interactive Leaflet map.
Required: title
Optional: data (lat/lon points or file path), config (map_type, center_lat, center_lon, zoom, theme)
Returns: {type, title, html_path, map_type}""",
    examples=[
        'report(action="map", title="Locations", data=[{"lat":-15.78,"lon":-47.93,"label":"Brasilia"}], config={"zoom":6})',
        'report(action="map", title="Stations", data="workspace/stations.csv", config={"map_type":"markers"})',
    ],
)
def run_map(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a Leaflet map. Delegates to the heavy maps builder."""
    from tools.report_ops import maps
    return maps.build(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
