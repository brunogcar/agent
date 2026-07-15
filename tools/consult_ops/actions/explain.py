"""tools/consult_ops/actions/explain.py — Concept explanation action.

Routes through consultor role with EXPLAIN_SYSTEM_PROMPT, which instructs
the model to act as a technical educator: use analogies, examples, and
step-by-step breakdowns; adapt depth to the question's sophistication;
structure with headers, bullet points, and code examples where helpful.

Use this action when the caller wants to UNDERSTAND something (concepts,
mechanisms, trade-offs) rather than get a recommendation (advise) or a
critique (review).
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
    EXPLAIN_SYSTEM_PROMPT,
    FORMAT_SUFFIXES,
    CONTEXT_TYPE_MODIFIERS,
)


@register_action(
    "consult", "explain",
    help_text="""explain — Educational concept explanation with analogies and step-by-step breakdowns.
Required: question (the concept to explain)
Optional: context (background material), trace_id, format (markdown|json|bullet_points), context_type (code|logs|architecture)
Returns: {explanation, provider, model, trace_id?, warnings?}""",
    examples=[
        'consult(action="explain", question="How does RAG differ from fine-tuning?")',
        'consult(action="explain", question="Explain the CAP theorem", context="We use Cassandra...", format="bullet_points")',
    ],
)
def _action_explain(
    question: str = "",
    context: str = "",
    trace_id: str = "",
    format: str = "markdown",
    context_type: str = "",
    **kwargs,
) -> dict:
    """Concept explanation. Calls consultor role with EXPLAIN_SYSTEM_PROMPT."""
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
        EXPLAIN_SYSTEM_PROMPT
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
        "action": "explain",
        "provider": provider,
        "model": result.model,
        "explanation": result.text,
    }
    if trace_id:
        response["trace_id"] = trace_id
    if warnings:
        response["warnings"] = warnings
    return response
