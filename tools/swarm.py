"""tools/swarm.py — Multi-model swarm meta-tool.

Routes all swarm actions to handlers in swarm_ops/actions/ via DISPATCH dict.
Auto-discovered by registry.py via @tool decorator.

The swarm calls multiple cloud LLM providers in parallel, collects responses,
and applies a strategy (consensus, race, vote, compare, or list_providers).

NOT parallel-safe (uses ThreadPoolExecutor internally — nested parallelism risk).
"""
from __future__ import annotations

import time

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

from tools import swarm_ops  # noqa: F401 — triggers DISPATCH auto-discovery
from tools.swarm_ops._registry import DISPATCH


@tool
@meta_tool(
    DISPATCH.get("swarm", {}),
    doc_sections=[
        "SWARM TOOL — Multi-model consultation:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Synthesized answer from multiple models | swarm(consensus) | All models answer, planner synthesizes best response |",
        " | Fastest valid answer | swarm(race) | First valid response wins, others cancelled |",
        " | Compare model agreement | swarm(vote) | All models answer, agreement analysis (unanimous/majority/split/disagreement) |",
        " | Side-by-side comparison | swarm(compare) | All responses returned without synthesis |",
        " | List available providers | swarm(list_providers) | Shows configured cloud providers + models |",
        "",
        "NOT parallel-safe — uses ThreadPoolExecutor internally.",
        "Requires cloud providers configured in .env (*_API_KEY + *_BASE_MODEL).",
    ],
)
def swarm(
    action: str,
    question: str = "",
    context: str = "",
    providers: str = "",
    max_tokens: int = 1024,
    timeout: int = 60,
    trace_id: str = "",
) -> dict:
    """Multi-model swarm meta-tool — consult multiple cloud LLMs in parallel."""
    action = action.strip().lower() if action else ""

    if not action:
        return fail("action is required", trace_id=trace_id)

    dispatch = DISPATCH.get("swarm", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
        )

    handler = op_info["func"]

    kwargs = {
        "question": question,
        "context": context,
        "providers": providers,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "trace_id": trace_id,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        return fail(f"Swarm action failed: {e}", trace_id=trace_id)

    if trace_id and "trace_id" not in result:
        result["trace_id"] = trace_id

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
