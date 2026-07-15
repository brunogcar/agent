"""tools/consult_ops/actions/review.py — Code review action.

Routes through consultor role with REVIEW_SYSTEM_PROMPT, which instructs
the model to produce a structured review with severity levels
(CRITICAL/WARNING/INFO) across 5 dimensions: correctness, security,
performance, maintainability, best practices.

Caller typically passes code in the `context` parameter and a focused
question (e.g. "Focus on the auth flow") in `question`. The `context_type`
modifier defaults to "code" semantics here — but it's still explicit so
callers can override (e.g. context_type="logs" to review operational
output instead of source).
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
    REVIEW_SYSTEM_PROMPT,
    FORMAT_SUFFIXES,
    CONTEXT_TYPE_MODIFIERS,
)


@register_action(
    "consult", "review",
    help_text="""review — Structured code review with severity-tagged findings.
Required: question (what to focus on), context (the code to review)
Optional: trace_id, format (markdown|json|bullet_points), context_type (code|logs|architecture)
Returns: {review, provider, model, trace_id?, warnings?}""",
    examples=[
        'consult(action="review", question="Focus on auth flow", context="<source code>")',
        'consult(action="review", question="Any race conditions?", context="<source>", format="json")',
    ],
)
def _action_review(
    question: str = "",
    context: str = "",
    trace_id: str = "",
    format: str = "markdown",
    context_type: str = "",
    **kwargs,
) -> dict:
    """Structured code review. Calls consultor role with REVIEW_SYSTEM_PROMPT."""
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
        REVIEW_SYSTEM_PROMPT
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
        "action": "review",
        "provider": provider,
        "model": result.model,
        "review": result.text,
    }
    if trace_id:
        response["trace_id"] = trace_id
    if warnings:
        response["warnings"] = warnings
    return response
