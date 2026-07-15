"""tools/consult_ops/actions/advise.py — General advisory action.

Preserves the original tools/consult.py behavior (single LLM call to the
consultor role with the ADVISE system prompt) but routes through the
consult_ops subpackage so the facade can dispatch via @meta_tool.

New v1.0 capabilities vs. the legacy consult():
  - trace_id: forwarded to llm.complete for observability threading.
  - format: markdown (default) | json | bullet_points — appends a format
    suffix to the system prompt.
  - context_type: "" (default) | code | logs | architecture — appends a
    context-type modifier to the system prompt.
"""
from __future__ import annotations

from tools.consult_ops._registry import register_action
from tools.consult_ops.helpers import (
    _check_consultor_available,
    _check_rate_limit,
    _truncate_context,
    _get_consultor_provider,
    _call_consultor,
)
from tools.consult_ops.prompts import (
    ADVISE_SYSTEM_PROMPT,
    FORMAT_SUFFIXES,
    CONTEXT_TYPE_MODIFIERS,
)


@register_action(
    "consult", "advise",
    help_text="""advise — General architectural advisory consultation (default action).
Required: question
Optional: context, trace_id, format (markdown|json|bullet_points), context_type (code|logs|architecture)
Returns: {advice, provider, model, trace_id?, warnings?}""",
    examples=[
        'consult(action="advise", question="How should I structure a plugin system?")',
        'consult(action="advise", question="Best way to handle retries?", context="We use httpx...", format="bullet_points")',
    ],
)
def _action_advise(
    question: str = "",
    context: str = "",
    trace_id: str = "",
    format: str = "markdown",
    context_type: str = "",
    **kwargs,
) -> dict:
    """General advisory consultation. Calls consultor role with ADVISE_SYSTEM_PROMPT."""
    if not question or not question.strip():
        return {
            "status": "error",
            "error": "The question parameter cannot be empty.",
            "trace_id": trace_id,
        }

    available, err = _check_consultor_available()
    if not available:
        if trace_id:
            err["trace_id"] = trace_id
        return err

    ok_rl, err = _check_rate_limit()
    if not ok_rl:
        if trace_id:
            err["trace_id"] = trace_id
        return err

    context, warnings = _truncate_context(context)

    provider = _get_consultor_provider()

    system_prompt = (
        ADVISE_SYSTEM_PROMPT
        + FORMAT_SUFFIXES.get(format, "")
        + CONTEXT_TYPE_MODIFIERS.get(context_type, "")
    )

    result = _call_consultor(
        system=system_prompt,
        user=question,
        context=context,
        trace_id=trace_id,
    )

    if not result.ok:
        return {
            "status": "error",
            "provider": provider,
            "model": result.model,
            "error": result.error,
            "trace_id": trace_id,
        }

    response = {
        "status": "success",
        "action": "advise",
        "provider": provider,
        "model": result.model,
        "advice": result.text,
    }
    if trace_id:
        response["trace_id"] = trace_id
    if warnings:
        response["warnings"] = warnings
    return response
