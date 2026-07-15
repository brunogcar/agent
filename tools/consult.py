"""tools/consult.py — Advisory consultation meta-tool (v1.0).

Thin @tool facade. Routes all consult actions to handlers in
consult_ops/actions/ via the DISPATCH dict. Auto-discovered by
registry.py via the @tool decorator.

v1.0 changes (the @meta_tool refactor):
  - Now a meta-tool with 3 actions: advise | review | explain.
  - @meta_tool auto-generates the action: Literal[...] type annotation and
    the docstring's action list from DISPATCH.
  - New params: trace_id (observability), format (markdown|json|bullet_points),
    context_type (code|logs|architecture|""), all forwarded to the handler.
  - All implementation logic moved to consult_ops/ subpackage.

NOT parallel-safe (uses LLM calls) — do NOT add to PARALLEL_SAFE.
The router's _RE_DIRECT_CONSULT heuristic already routes "ask another model"
intents directly here; no router changes needed for v1.0.
"""
from __future__ import annotations

import time

from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import consult_ops to trigger DISPATCH auto-discovery BEFORE @meta_tool reads it.
from tools import consult_ops  # noqa: F401
from tools.consult_ops._registry import DISPATCH


@tool
@meta_tool(
    DISPATCH.get("consult", {}),
    doc_sections=[
        "CONSULT TOOL — Advisory consultation (single LLM call to consultor role):",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Architectural advice / deadlock breaker | consult(advise) | General advisory prompt (default behavior pre-v1.0) |",
        " | Structured code review | consult(review) | Severity-tagged findings across correctness/security/perf/maintainability/best-practices |",
        " | Concept explanation | consult(explain) | Educational prompt with analogies + step-by-step breakdowns |",
        "",
        "PARAMETERS:",
        " - question (required for all actions) — what you want the consultor to address.",
        " - context (optional) — supporting material; truncated to ~2000 tokens to prevent overflow.",
        " - format: markdown (default) | json | bullet_points — controls output shape.",
        " - context_type: '' (default) | code | logs | architecture — focuses the prompt on the context kind.",
        " - trace_id (optional) — forwarded to llm.complete for observability threading.",
        "",
        "NOT parallel-safe — uses LLM calls. Kill switch: empty CONSULTOR_MODEL in .env.",
    ],
)
def consult(
    action: str = "",
    question: str = "",
    context: str = "",
    trace_id: str = "",
    format: str = "markdown",
    context_type: str = "",
) -> dict:
    """Advisory consultation meta-tool — advise | review | explain."""
    action = action.strip().lower() if action else ""

    tracer.step(trace_id, "consult", f"action={action}")

    if not action:
        return {
            "status": "error",
            "error": "action is required (advise | explain | review)",
            "trace_id": trace_id,
        }

    dispatch = DISPATCH.get("consult", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return {
            "status": "error",
            "error": f"Unknown action '{action}'. Use: {valid_actions}",
            "trace_id": trace_id,
        }

    handler = op_info["func"]

    kwargs = {
        "question": question,
        "context": context,
        "trace_id": trace_id,
        "format": format,
        "context_type": context_type,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Consult action failed: {e}",
            "trace_id": trace_id,
        }

    if not isinstance(result, dict):
        return {
            "status": "error",
            "error": f"Handler returned {type(result).__name__}, expected dict.",
            "trace_id": trace_id,
        }

    if result.get("status") == "error":
        tracer.step(trace_id, "consult", f"action={action}:failed")
    else:
        tracer.step(trace_id, "consult", f"action={action}:complete")

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
