"""Agent clear_cache action — clear the response cache.

Useful for testing and debugging deterministic roles.
"""
from __future__ import annotations

from tools.agent_ops._registry import register_action
from tools.agent_ops.cache import _clear_cache


HELP_CLEAR_CACHE = """
clear_cache
Clear the response cache for deterministic roles (classify, route).
No parameters required.
Returns: {status, message}
"""


@register_action(
    "agent",
    "clear_cache",
    help_text=HELP_CLEAR_CACHE,
    examples=[
        'agent(action="clear_cache")',
    ],
)
def run_clear_cache(**kwargs) -> dict:
    """Clear the agent response cache."""
    _clear_cache()
    return {
        "status": "success",
        "message": "Agent response cache cleared.",
    }
