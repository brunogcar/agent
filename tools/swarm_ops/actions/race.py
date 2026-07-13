"""Swarm action: race — all models answer, first valid response wins.

v1.0.2 (cross-LLM):
  - P1-3: Whitespace-only responses no longer count as valid winners.
  - P3-4 (Kimi): Added `successful_count` to the result for parity with
    consensus/compare/vote (was missing — callers couldn't tell how many
    providers succeeded without inspecting the responses array).
"""
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
Returns: {winner: {...}, responses: [...], provider_count, successful_count}""",
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

    # v1.0.2 (P1-3 cross-LLM): Use .strip() so whitespace-only responses
    # don't win the race. A provider returning "   " (e.g. content-filter
    # blanking) should not be declared the winner.
    winner = None
    for r in results:
        if r["text"].strip() and not r["error"]:
            winner = r
            break

    if not winner:
        return fail("All providers failed to respond.", responses=results)

    # v1.0.2 (P3-4 cross-LLM): Add successful_count for parity with other actions.
    successful_count = sum(1 for r in results if r["text"].strip() and not r["error"])

    return ok({
        "winner": winner,
        "responses": results,
        "provider_count": len(available),
        "successful_count": successful_count,
    })
