"""
tools/consult.py - Explicit Advisory Tool.
"""
from __future__ import annotations

from registry import tool
from core.llm import llm
from core.config import cfg
from core.llm_backend.budget import check_rate_limit

_MAX_CONTEXT_CHARS = 4000

_ADVISORY_SYSTEM_PROMPT = (
    "You are an expert advisory consultant. Provide clear, concise, and highly actionable advice. "
    "Focus on architectural soundness, best practices, and potential pitfalls. "
    "Do not write code unless explicitly asked. Keep responses structured and easy to read."
)

@tool
def consult(question: str, context: str = "") -> dict:
    """
    Consult the configured AI advisor for high-level help.
    Use for breaking deadlocks, architectural decisions, or complex logic reviews.
    Do not use for routine code generation or simple questions.
    """
    if not cfg.consultor_model:
        return {
            "status": "disabled",
            "error": "Consultor is disabled. Set CONSULTOR_MODEL in .env to enable.",
        }

    if not question or not question.strip():
        return {"status": "error", "error": "The question parameter cannot be empty."}

    # Get provider name for rate limiting
    provider = cfg.model_registry.get("consultor", {}).get("provider", "unknown")

    # Check rate limit before making the cloud call
    if not check_rate_limit(provider):
        return {
            "status": "rate_limited",
            "error": f"Rate limit exceeded for {provider}. Please wait before consulting again.",
        }

    # Context truncation guardrail
    truncated_warning = None
    if len(context) > _MAX_CONTEXT_CHARS:
        context = context[:_MAX_CONTEXT_CHARS] + "\n\n[WARNING: Context truncated to 4000 chars.]"
        truncated_warning = "Context was truncated to 4000 characters."

    result = llm.complete(
        role="consultor",
        system=_ADVISORY_SYSTEM_PROMPT,
        user=question,
        context=context,
    )

    if not result.ok:
        return {
            "status": "error",
            "provider": provider,
            "model": result.model,
            "error": result.error,
        }

    response = {
        "status": "success",
        "provider": provider,
        "model": result.model,
        "advice": result.text,
    }

    if truncated_warning:
        response["warning"] = truncated_warning

    return response
