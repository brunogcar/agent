"""tools/swarm.py — Multi-model swarm meta-tool.

Routes all swarm actions to handlers in swarm_ops/actions/ via DISPATCH dict.
Auto-discovered by registry.py via @tool decorator.

The swarm calls multiple cloud LLM providers in parallel, collects responses,
and applies a strategy (consensus, race, vote, compare, or list_providers).

NOT parallel-safe (uses ThreadPoolExecutor internally — nested parallelism risk).

v1.0.1: Added input validation for max_tokens / timeout (P3-2).
v1.0.2 (P2-4 cross-LLM): Changed error_code from INVALID_ACTION to INVALID_INPUT
        for parameter validation failures (semantically correct — the action
        is valid, the parameter value is not).
"""
from __future__ import annotations

import time

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

from tools import swarm_ops  # noqa: F401 — triggers DISPATCH auto-discovery
from tools.swarm_ops._registry import DISPATCH


# v1.0.1: Per-call bounds for max_tokens and timeout. Tight enough to catch
# obviously-wrong inputs (negative, zero, runaway), loose enough to not
# constrain legitimate use. max_tokens upper bound matches the largest
# common cloud context (8192); timeout upper bound (300s) matches the
# planner role's hard ceiling.
_MAX_TOKENS_MIN = 1
_MAX_TOKENS_MAX = 8192
_TIMEOUT_MIN = 1
_TIMEOUT_MAX = 300


@tool
@meta_tool(
    DISPATCH.get("swarm", {}),
    doc_sections=[
        "SWARM TOOL — Multi-model consultation:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Synthesized answer from multiple models | swarm(consensus) | All models answer, planner synthesizes best response |",
        " | Fastest valid answer | swarm(race) | First valid response wins, others cancelled |",
        " | Compare model agreement | swarm(vote) | All models answer, agreement analysis (unanimous/majority/split/disagreement/single_response) |",
        " | Side-by-side comparison | swarm(compare) | All responses returned without synthesis |",
        " | List available providers | swarm(list_providers) | Shows configured cloud providers + models |",
        "",
        "NOT parallel-safe — uses ThreadPoolExecutor internally.",
        "Requires cloud providers configured in .env (*_API_KEY + *_BASE_MODEL).",
        f"max_tokens bounds: [{_MAX_TOKENS_MIN}, {_MAX_TOKENS_MAX}]; timeout bounds: [{_TIMEOUT_MIN}, {_TIMEOUT_MAX}] seconds.",
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
    temperature: float = -1.0,
    json_mode: bool = False,
    json_schema: str = "",
) -> dict:
    """Multi-model swarm meta-tool — consult multiple cloud LLMs in parallel.

    [v1.1] Added temperature, json_mode, json_schema params:
    - temperature: -1.0 = use default (0.7); 0.0 = deterministic (for vote)
    - json_mode: True = request JSON output from providers
    - json_schema: JSON schema string for structured output enforcement
      (ignored by Claude/Gemini — they use different mechanisms)
    """
    action = action.strip().lower() if action else ""

    if not action:
        return fail("action is required", trace_id=trace_id)

    # v1.0.1: Validate numeric bounds before dispatch. Negative/zero values
    # would otherwise reach provider.chat_completion() and produce confusing
    # downstream errors (OpenAI rejects, Gemini may hang, as_completed(timeout=9)
    # on timeout=-1 raises ValueError). list_providers ignores these params
    # but we validate unconditionally — the fail message is clearer than a
    # downstream 400.
    # v1.0.2 (P2-4): error_code is INVALID_INPUT (not INVALID_ACTION — the
    # action name is valid, the parameter value is not).
    if not (_MAX_TOKENS_MIN <= max_tokens <= _MAX_TOKENS_MAX):
        return fail(
            f"max_tokens must be between {_MAX_TOKENS_MIN} and {_MAX_TOKENS_MAX}, got {max_tokens}",
            trace_id=trace_id,
            error_code="INVALID_INPUT",
        )
    if not (_TIMEOUT_MIN <= timeout <= _TIMEOUT_MAX):
        return fail(
            f"timeout must be between {_TIMEOUT_MIN} and {_TIMEOUT_MAX} seconds, got {timeout}",
            trace_id=trace_id,
            error_code="INVALID_INPUT",
        )

    dispatch = DISPATCH.get("swarm", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
            error_code="INVALID_ACTION",
        )

    handler = op_info["func"]

    # [v1.1 #21+#20] Parse temperature, json_mode, json_schema for passthrough.
    # temperature: -1.0 = default (0.7); otherwise use the caller's value.
    actual_temp = 0.7 if temperature < 0 else temperature

    # json_schema: parse JSON string to dict (like agent facade does).
    parsed_schema = None
    if json_schema:
        if isinstance(json_schema, str):
            try:
                import json as _json
                parsed_schema = _json.loads(json_schema)
            except _json.JSONDecodeError:
                return fail(
                    f"json_schema must be valid JSON — got: {json_schema[:100]}",
                    trace_id=trace_id,
                    error_code="INVALID_INPUT",
                )
        elif isinstance(json_schema, dict):
            parsed_schema = json_schema

    kwargs = {
        "question": question,
        "context": context,
        "providers": providers,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "trace_id": trace_id,
        # [v1.1] Provider capability passthrough
        "temperature": actual_temp,
        "json_mode": json_mode,
        "json_schema": parsed_schema,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        # v1.0.2 (P3-5 cross-LLM): log the traceback so programming errors
        # (KeyError, AttributeError) aren't silently swallowed. The user-facing
        # error message stays the same; the trace gets the full context.
        tracer.error(trace_id, "swarm", f"Handler crash in action={action!r}: {e}")
        return fail(f"Swarm action failed: {e}", trace_id=trace_id)

    if trace_id and "trace_id" not in result:
        result["trace_id"] = trace_id

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
