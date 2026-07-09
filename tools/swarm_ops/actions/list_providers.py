"""Swarm action: list_providers — list all configured cloud providers."""
from __future__ import annotations
import os
from tools.swarm_ops._registry import register_action
from tools.swarm_ops.helpers import _get_available_providers
from core.contracts import ok


@register_action(
    "swarm", "list_providers",
    help_text="""list_providers — List all configured cloud providers available for swarm.
No parameters required.
Returns: {providers: [{name, model, available}], count}""",
    examples=[
        'swarm(action="list_providers")',
    ],
)
def _action_list_providers(**kwargs) -> dict:
    available = _get_available_providers()

    provider_list = [
        {
            "name": name,
            "model": model,
            "available": True,
        }
        for name, model, _ in available
    ]

    return ok({
        "providers": provider_list,
        "count": len(provider_list),
    })
