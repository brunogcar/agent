"""Agent metrics action — bypass for in-memory metrics query.

Returns per-role metrics and parse warnings without calling the LLM.
"""
from __future__ import annotations

from tools.agent_core._registry import register_action
from tools.agent_core.metrics import _get_metrics
from tools.agent_core.parse_warnings import _get_parse_warnings


HELP_METRICS = """
metrics
Query per-role metrics and parse warnings. No LLM call.
Optional: task (role name to filter, or empty for all)
Returns: {status, role, metrics, parse_warnings}
"""


@register_action(
    "agent",
    "metrics",
    help_text=HELP_METRICS,
    examples=[
        'agent(action="metrics", task="classify")',
        'agent(action="metrics")',
    ],
)
def run_metrics(task: str = "", **kwargs) -> dict:
    """Return in-memory metrics and parse warnings."""
    target = task.strip() if task else None
    return {
        "status": "success",
        "role": "metrics",
        "metrics": _get_metrics(target),
        "parse_warnings": _get_parse_warnings(target),
    }
