"""Swarm action: vote — all models answer, responses compared for agreement.

v1.0.1: Agreement classification fixed.
  - `single_response`: only 1 provider succeeded (was misclassified as
    `unanimous` — a single voter cannot be "unanimous"). This matters for
    autocode's debug-loop confidence map (vcs_ops.py: confidence_map),
    where `unanimous` → HIGH skips the low-confidence PR comment.
  - `split` vs `disagreement`: 2 distinct texts with 2 successful voters
    is now `split` (was misclassified as `disagreement` due to a
    `len(successful) > 2` guard).
"""
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
Returns: {responses: [...], agreement: str, provider_count, successful_count}

agreement is one of:
  unanimous       — all successful providers (>=2) returned the same normalized text
  majority        — exactly 2 distinct texts, largest group > 50% of successful
  split           — exactly 2 distinct texts, no group > 50% (incl. 2v2 tie)
  disagreement    — 3+ distinct texts
  single_response — only 1 provider succeeded (no agreement to measure)""",
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

    n_successful = len(successful)
    n_distinct = len(normalized)

    # v1.0.1: Classification — see module docstring + API.md agreement table.
    if n_successful < 2:
        # A single voter cannot express agreement. Previously misclassified
        # as "unanimous", which downstream consumers (autocode debug-loop
        # confidence map) treat as HIGH confidence. Use a distinct label so
        # consumers can route single-response verdicts to a review path.
        agreement = "single_response"
    elif n_distinct == 1:
        agreement = "unanimous"
    elif n_distinct == 2:
        # Majority requires the largest group to strictly exceed 50%.
        # A 2v2 tie (or any NvN tie) is a split — no group has > 50%.
        counts = {k: len(v) for k, v in normalized.items()}
        max_count = max(counts.values())
        if max_count > n_successful / 2:
            agreement = "majority"
        else:
            agreement = "split"
    else:
        # 3+ distinct normalized texts
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
