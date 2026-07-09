"""Swarm action: vote — all models answer, responses compared for agreement."""
from __future__ import annotations
from tools.swarm_ops._registry import register_action
from tools.swarm_ops.helpers import (
    _get_available_providers, _call_all_providers, _SWARM_SYSTEM_PROMPT,
)
from core.contracts import ok, fail


@register_action(
    "swarm", "vote",
    help_text="""vote — Ask all providers, compare responses for agreement/disagreement.
Use for classification, routing, or review decisions where majority matters.
Required: question
Optional: context, providers (comma-separated filter)
Returns: {responses: [...], agreement: str, provider_count, successful_count}""",
    examples=[
        'swarm(action="vote", question="Is this code safe to deploy? Answer YES or NO.")',
        'swarm(action="vote", question="Classify this email as spam or not spam: ...", providers="openai,claude,gemini")',
    ],
)
def _action_vote(
    question: str = "",
    context: str = "",
    providers: str = "",
    timeout: int = 60,
    max_tokens: int = 1024,
    **kwargs,
) -> dict:
    if not question:
        return fail("question is required for vote")

    available = _get_available_providers(providers)
    if not available:
        return fail("No cloud providers configured. Set *_API_KEY and *_BASE_MODEL in .env to enable.")

    results = _call_all_providers(
        available, _SWARM_SYSTEM_PROMPT, question, context, timeout, max_tokens
    )

    successful = [r for r in results if r["text"] and not r["error"]]
    if not successful:
        return fail("All providers failed to respond.", responses=results)

    # Simple agreement analysis: group by normalized response text
    normalized = {}
    for r in successful:
        key = r["text"].strip().lower()[:200]  # normalize for comparison
        if key not in normalized:
            normalized[key] = []
        normalized[key].append(r["provider"])

    if len(normalized) == 1:
        agreement = "unanimous"
    elif len(normalized) == 2 and len(successful) > 2:
        # Check for majority
        counts = {k: len(v) for k, v in normalized.items()}
        max_count = max(counts.values())
        if max_count > len(successful) / 2:
            agreement = "majority"
        else:
            agreement = "split"
    else:
        agreement = "disagreement"

    # Build agreement summary
    groups = []
    for key, provider_list in normalized.items():
        groups.append({
            "providers": provider_list,
            "count": len(provider_list),
            "preview": key[:100],
        })
    groups.sort(key=lambda g: g["count"], reverse=True)

    return ok({
        "responses": results,
        "agreement": agreement,
        "groups": groups,
        "provider_count": len(available),
        "successful_count": len(successful),
    })
