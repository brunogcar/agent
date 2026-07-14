"""Swarm action: compare — all models answer, responses returned side-by-side.

v1.0.2 (P1-3 cross-LLM): Whitespace-only responses no longer count as successful.
"""
from __future__ import annotations
from tools.swarm_ops._registry import register_action
from tools.swarm_ops.helpers import (
    _get_available_providers, _call_all_providers, _SWARM_SYSTEM_PROMPT,
)
from core.contracts import ok, fail


@register_action(
    "swarm", "compare",
    help_text="""compare — Ask all providers, return responses side-by-side (no synthesis).
Use to compare model outputs directly without a synthesis step.
Required: question
Optional: context, providers (comma-separated filter)
Returns: {responses: [...], provider_count, successful_count}""",
    examples=[
        'swarm(action="compare", question="Explain RAFT consensus in 3 sentences.")',
        'swarm(action="compare", question="Best practices for error handling in Python?", providers="openai,claude")',
    ],
)
def _action_compare(
    question: str = "",
    context: str = "",
    providers: str = "",
    timeout: int = 60,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    json_mode: bool = False,
    json_schema: dict | None = None,
    **kwargs,
) -> dict:
    if not question:
        return fail("question is required for compare")

    available = _get_available_providers(providers)
    if not available:
        return fail("No cloud providers configured. Set *_API_KEY and *_BASE_MODEL in .env to enable.")

    # [v1.1 #21+#20] Pass through provider-capability params. compare callers
    # typically want temperature=0 to see raw model differences (not sampling
    # variation) and may use json_schema to get structured side-by-side output.
    results = _call_all_providers(
        available, _SWARM_SYSTEM_PROMPT, question, context, timeout, max_tokens,
        temperature=temperature, json_mode=json_mode, json_schema=json_schema,
    )

    # v1.0.2 (P1-3 cross-LLM): Use .strip() so whitespace-only responses
    # are not counted as successful.
    successful = [r for r in results if r["text"].strip() and not r["error"]]
    if not successful:
        return fail("All providers failed to respond.", responses=results)

    return ok({
        "responses": results,
        "provider_count": len(available),
        "successful_count": len(successful),
    })
