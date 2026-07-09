"""Swarm action: consensus — all models answer, planner synthesizes."""
from __future__ import annotations
from tools.swarm_ops._registry import register_action
from tools.swarm_ops.helpers import (
    _get_available_providers, _call_all_providers, _SWARM_SYSTEM_PROMPT,
)
from core.contracts import ok, fail


@register_action(
    "swarm", "consensus",
    help_text="""consensus — Ask all configured cloud providers, synthesize best answer.
Required: question
Optional: context, providers (comma-separated filter, e.g. "openai,deepseek")
Returns: {responses: [...], synthesis: str, provider_count, successful_count}""",
    examples=[
        'swarm(action="consensus", question="How to handle concurrent writes in SQLite?")',
        'swarm(action="consensus", question="Best architecture for a chat app?", providers="openai,claude")',
    ],
)
def _action_consensus(
    question: str = "",
    context: str = "",
    providers: str = "",
    timeout: int = 60,
    max_tokens: int = 1024,
    **kwargs,
) -> dict:
    if not question:
        return fail("question is required for consensus")

    available = _get_available_providers(providers)
    if not available:
        return fail("No cloud providers configured. Set *_API_KEY and *_BASE_MODEL in .env to enable.")

    results = _call_all_providers(
        available, _SWARM_SYSTEM_PROMPT, question, context, timeout, max_tokens
    )

    successful = [r for r in results if r["text"] and not r["error"]]
    if not successful:
        return fail("All providers failed to respond.", responses=results)

    # Synthesize using planner
    from core.llm import llm
    formatted = "\n\n---\n\n".join(
        f"**{r['provider']} ({r['model']}):**\n{r['text']}"
        for r in successful
    )
    synthesis = llm.complete(
        role="planner",
        system=(
            "You are a synthesis specialist. Given multiple AI responses to the "
            "same question, synthesize the best answer by combining the strongest "
            "points from each response. Note any disagreements between the models. "
            "Output only the synthesized answer."
        ),
        user=f"Question: {question}\n\nResponses from {len(successful)} AI models:\n\n{formatted}",
    )

    return ok({
        "responses": results,
        "synthesis": synthesis.text if synthesis.ok else "",
        "provider_count": len(available),
        "successful_count": len(successful),
    })
