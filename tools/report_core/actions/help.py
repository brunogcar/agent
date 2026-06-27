"""Help action handler — returns detailed metadata for a specific action.

No heavy imports. Uses the in-memory DISPATCH and DISPATCH_METADATA tables.
"""
from __future__ import annotations

from typing import Any

from tools.report_core._registry import register_action, DISPATCH, DISPATCH_METADATA


@register_action(
    "report",
    "help",
    help_text="""Get detailed help for a specific report action.
data: action name to get help for (e.g., "chart", "dashboard")
Returns: {type, action, description, required_params, optional_params, config_keys}
If data is empty, returns help for all actions.""",
    examples=[
        'report(action="help", data="chart")',
        'report(action="help")',
    ],
)
def run_help(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Return detailed metadata for one or all report actions."""
    target = (data or "").strip().lower() if isinstance(data, str) else ""
    report_dispatch = DISPATCH.get("report", {})

    if target:
        if target not in report_dispatch:
            return {
                "type": "help",
                "error": f"Unknown action '{target}'",
                "known_actions": list(report_dispatch.keys()),
            }
        meta = DISPATCH_METADATA.get(target, {})
        return {
            "type": "help",
            "action": target,
            "description": meta.get("description", ""),
            "required_params": meta.get("required_params", []),
            "optional_params": meta.get("optional_params", []),
            "config_keys": meta.get("config_keys", []),
        }

    # Return all actions' metadata
    all_help = {}
    for name in sorted(report_dispatch.keys()):
        meta = DISPATCH_METADATA.get(name, {})
        all_help[name] = {
            "description": meta.get("description", ""),
            "required_params": meta.get("required_params", []),
            "optional_params": meta.get("optional_params", []),
            "config_keys": meta.get("config_keys", []),
        }
    return {
        "type": "help",
        "actions": all_help,
        "count": len(all_help),
    }
