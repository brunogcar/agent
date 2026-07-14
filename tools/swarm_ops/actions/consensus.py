"""Swarm action: consensus — all models answer, planner synthesizes.

v1.0.2 (cross-LLM):
  - P1-3: Whitespace-only responses no longer count as successful.
  - P1-5: Synthesis failure is now surfaced via `synthesis_failed` /
    `synthesis_error` fields instead of silently returning empty string.
  - P2-5: Synthesis call now passes `trace_id` and `max_tokens` through.
  - P2-6: Synthesis prompt now includes the `context` (was dropped).
  - P2-7: Per-provider responses truncated to 2000 chars before synthesis
    to avoid context-overflow with 5 providers × long responses.
"""
from __future__ import annotations
from tools.swarm_ops._registry import register_action
from tools.swarm_ops.helpers import (
    _get_available_providers, _call_all_providers, _SWARM_SYSTEM_PROMPT,
)
from core.contracts import ok, fail

# v1.0.2 (P2-7 cross-LLM): Per-response truncation before synthesis. With 5
# providers each returning ~2000-token responses, the synthesis prompt could
# hit 10k+ input tokens — exceeding small planner context windows. 2000 chars
# (~500 tokens) per response keeps the synthesis prompt bounded.
_SYNTHESIS_RESPONSE_TRUNCATE = 2000


@register_action(
    "swarm", "consensus",
    help_text="""consensus — Ask all configured cloud providers, synthesize best answer.
Required: question
Optional: context, providers (comma-separated filter, e.g. "openai,deepseek")
Returns: {responses: [...], synthesis: str, synthesis_failed: bool, synthesis_error: str, provider_count, successful_count}""",
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
    temperature: float = 0.7,
    json_mode: bool = False,
    json_schema: dict | None = None,
    **kwargs,
) -> dict:
    if not question:
        return fail("question is required for consensus")

    available = _get_available_providers(providers)
    if not available:
        return fail("No cloud providers configured. Set *_API_KEY and *_BASE_MODEL in .env to enable.")

    # [v1.1 #21+#20] Pass through provider-capability params. temperature lets
    # callers trade creativity for determinism (default 0.7 = balanced).
    # json_mode + json_schema request structured output (ignored by
    # Claude/Gemini — see docs/core/llm/INSTRUCTIONS.md rule #12).
    results = _call_all_providers(
        available, _SWARM_SYSTEM_PROMPT, question, context, timeout, max_tokens,
        temperature=temperature, json_mode=json_mode, json_schema=json_schema,
    )

    # v1.0.2 (P1-3 cross-LLM): Use .strip() so whitespace-only responses
    # ("   ") are not counted as successful. Previously, "   " was truthy
    # and passed the filter, then normalized to "" in vote — causing false
    # unanimity. Same fix applied to race.py and compare.py.
    successful = [r for r in results if r["text"].strip() and not r["error"]]
    if not successful:
        return fail("All providers failed to respond.", responses=results)

    # Synthesize using planner
    from core.llm import llm
    # v1.0.2 (P2-7 cross-LLM): Truncate per-response to bound synthesis prompt size.
    formatted = "\n\n---\n\n".join(
        f"**{r['provider']} ({r['model']}):**\n{r['text'][:_SYNTHESIS_RESPONSE_TRUNCATE]}"
        for r in successful
    )
    # v1.0.2 (P2-6 cross-LLM): Include context in synthesis prompt (was dropped).
    context_block = f"Context:\n{context}\n\n" if context else ""
    # v1.0.2 (P2-5 cross-LLM): Pass trace_id + max_tokens through so synthesis
    # is traced and respects the caller's token budget.
    trace_id = kwargs.get("trace_id", "")
    synthesis = llm.complete(
        role="planner",
        system=(
            "You are a synthesis specialist. Given multiple AI responses to the "
            "same question, synthesize the best answer by combining the strongest "
            "points from each response. Note any disagreements between the models. "
            "Output only the synthesized answer."
        ),
        user=f"{context_block}Question: {question}\n\nResponses from {len(successful)} AI models:\n\n{formatted}",
        trace_id=trace_id,
        max_tokens=max_tokens,
    )

    # v1.0.2 (P1-5 cross-LLM): Surface synthesis failure instead of silently
    # returning empty string. The action still succeeds (provider responses
    # are valuable), but callers can check `synthesis_failed` to know whether
    # the planner crashed. `synthesis_error` carries the error message.
    return ok({
        "responses": results,
        "synthesis": synthesis.text if synthesis.ok else "",
        "synthesis_failed": not synthesis.ok,
        "synthesis_error": "" if synthesis.ok else (synthesis.error or "unknown synthesis failure"),
        "provider_count": len(available),
        "successful_count": len(successful),
    })
