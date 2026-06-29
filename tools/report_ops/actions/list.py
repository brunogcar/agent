"""List action handler — returns all available report actions.

No heavy imports. Uses the in-memory DISPATCH and DISPATCH_METADATA tables.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops._registry import register_action, DISPATCH, DISPATCH_METADATA


@register_action(
    "report",
    "list",
    help_text="""List all available report actions with descriptions.
Returns: {type, actions, count}
No required params.""",
    examples=[
        'report(action="list")',
    ],
)
def run_list(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Return a catalog of all registered report actions."""
    actions = []
    for name in sorted(DISPATCH.get("report", {}).keys()):
        meta = DISPATCH_METADATA.get(name, {})
        actions.append({
            "name": name,
            "description": meta.get("description", ""),
            "required_params": meta.get("required_params", []),
            "optional_params": meta.get("optional_params", []),
            "config_keys": meta.get("config_keys", []),
        })
    return {
        "type": "list",
        "actions": actions,
        "count": len(actions),
    }
