"""
report_core/maps.py - Leaflet.js map builders.

Client-side rendering. Produces JSON config for the template.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.report_core.data import load_data
from tools.report_core.paths import report_out_dir


def build(
    trace_id: str,
    title: str,
    data: Any,
    config: dict,
) -> dict:
    """Build a Leaflet map and return HTML path."""
    data_path = config.get("data_path", "")
    loaded, err = load_data(data=data, data_path=data_path)
    if err:
        raise ValueError(err)

    map_type = config.get("map_type", "markers").lower()
    center_lat = config.get("center_lat")
    center_lon = config.get("center_lon")
    zoom = config.get("zoom", 5)

    # Normalize center (fix equator/prime-meridian bug)
    if center_lat is None:
        center_lat = -15.78
    if center_lon is None:
        center_lon = -47.93

    map_config = {
        "map_type": map_type,
        "center": [center_lat, center_lon],
        "zoom": zoom,
        "data": loaded,
        "theme": config.get("theme", "dark"),
    }

    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "map"))
    html_path = out_dir / f"{safe_title}.html"

    from tools.report_core import html
    ctx = {
        "title": title,
        "map_config_json": json.dumps(map_config),
        "theme": config.get("theme", "dark"),
    }
    html.render_template("map.html", ctx, html_path)

    return {
        "type": "map",
        "title": title,
        "html_path": str(html_path),
        "map_type": map_type,
    }
