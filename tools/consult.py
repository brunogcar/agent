"""
tools/consult.py - Explicit Advisory Tool.
"""
from __future__ import annotations

from registry import tool
from core.llm import llm
from core.config import cfg
from core.llm_backend.budget import check_rate_limit

_MAX_CONTEXT_TOKENS = 2000  # Conservative default for cloud models

# Attempt to import tiktoken for accurate token counting, fallback to char estimate
try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:
    _HAS_TIKTOKEN = False

def _estimate_tokens(text: str) -> int:
    if _HAS_TIKTOKEN:
        try:
            encoder = tiktoken.get_encoding("cl100k_base")
            return len(encoder.encode(text))
        except Exception:
            pass
    # Fallback: ~4 chars per token is a safe conservative estimate
    return len(text) // 4

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

    # Pre-flight check: verify the role's provider is available
    if not llm.is_available("consultor"):
        return {
            "status": "disabled",
            "error": f"Provider for consultor role ('{provider}') is not available or not configured.",
        }

    # Check rate limit before making the cloud call
    if not check_rate_limit(provider):
        return {
            "status": "rate_limited",
            "error": f"Rate limit exceeded for {provider}. Please wait before consulting again.",
        }

    # Token-aware context truncation guardrail
    warnings = []
    current_tokens = _estimate_tokens(context)
    if current_tokens > _MAX_CONTEXT_TOKENS:
        if _HAS_TIKTOKEN:
            try:
                encoder = tiktoken.get_encoding("cl100k_base")
                tokens = encoder.encode(context)
                context = encoder.decode(tokens[:_MAX_CONTEXT_TOKENS])
            except Exception:
                context = context[: _MAX_CONTEXT_TOKENS * 4]
        else:
            context = context[: _MAX_CONTEXT_TOKENS * 4]
        
        warnings.append(f"Context truncated from ~{current_tokens} to {_MAX_CONTEXT_TOKENS} tokens to prevent overflow.")

    # Execute LLM Call (llm.complete handles the timeout from RoleConfig)
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

    if warnings:
        response["warnings"] = warnings

    return response
