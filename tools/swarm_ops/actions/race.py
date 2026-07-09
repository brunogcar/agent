"""Swarm action: race — all models answer, first valid response wins."""
from __future__ import annotations
from tools.swarm_ops._registry import register_action
from tools.swarm_ops.helpers import (
    _get_available_providers, _call_providers_race, _SWARM_SYSTEM_PROMPT,
)
from core.contracts import ok, fail


@register_action(
    "swarm", "race",
    help_text="""race — Ask all providers, return first valid response (fastest wins).
Required: question
Optional: context, providers (comma-separated filter)
Returns: {winner: {...}, responses: [...], provider_count}""",
    examples=[
        'swarm(action="race", question="What is the capital of France?")',
        'swarm(action="race", question="Quick fact: who invented Python?", providers="openai,deepseek")',
    ],
)
def _action_race(
    question: str = "",
    context: str = "",
    providers: str = "",
    timeout: int = 60,
    max_tokens: int = 1024,
    **kwargs,
) -> dict:
    if not question:
        return fail("question is required for race")

    available = _get_available_providers(providers)
    if not available:
        return fail("No cloud providers configured. Set *_API_KEY and *_BASE_MODEL in .env to enable.")

    results = _call_providers_race(
        available, _SWARM_SYSTEM_PROMPT, question, context, timeout, max_tokens
    )

    winner = None
    for r in results:
        if r["text"] and not r["error"]:
            winner = r
            break

    if not winner:
        return fail("All providers failed to respond.", responses=results)

    return ok({
        "winner": winner,
        "responses": results,
        "provider_count": len(available),
    })
