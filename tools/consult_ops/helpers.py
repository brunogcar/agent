"""tools/consult_ops/helpers.py — Shared utilities for consult actions.

Extracted from the original 111-line tools/consult.py during the v1.0
@meta_tool refactor. These helpers are pure functions with no side effects
beyond what their names imply (token counting, context truncation, kill
switch + rate-limit pre-flight checks), so they can be unit-tested in
isolation by tests/tools/consult/test_helpers.py.

[DESIGN] KEY INVARIANTS — read before modifying:
  1. _MAX_CONTEXT_TOKENS is a soft cap on the `context` parameter (NOT the
     user question or system prompt). Cloud consultor models have varying
     context windows; 2000 tokens is a conservative default that works for
     all configured providers without overruns.
  2. _estimate_tokens() prefers tiktoken when available and falls back to
     a char-count heuristic (len // 4). The fallback MUST stay conservative
     — underestimating tokens risks context-window overruns; overestimating
     just triggers earlier truncation (safe).
  3. _check_consultor_available() returns (ok, error_dict). When ok=False
     the error_dict has status="disabled" — distinct from "error" so the
     router / caller can distinguish "feature turned off" from "LLM blew up".
  4. _check_rate_limit() returns (ok, error_dict) with status="rate_limited"
     on failure. It wraps check_rate_limit() from core.llm_backend.rate_limit
     so action handlers don't import rate_limit directly — keeps the action
     modules thin and test-friendly.
"""
from __future__ import annotations

from typing import Tuple

from core.config import cfg
from core.llm import llm
from core.llm_backend.rate_limit import check_rate_limit

_MAX_CONTEXT_TOKENS = 2000  # Conservative default for cloud models

# tiktoken is an optional dependency. We import lazily so the module imports
# cleanly even if tiktoken isn't installed; _estimate_tokens falls back to a
# char-count heuristic when _HAS_TIKTOKEN is False.
try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:
    _HAS_TIKTOKEN = False


def _estimate_tokens(text: str) -> int:
    """Estimate token count for `text`.

    Uses tiktoken cl100k_base encoding when available (matches GPT-4o / GPT-3.5
    tokenization closely enough for budgeting purposes). Falls back to a
    conservative char-count heuristic (~4 chars/token) on ImportError or any
    encoder failure.
    """
    if _HAS_TIKTOKEN:
        try:
            encoder = tiktoken.get_encoding("cl100k_base")
            return len(encoder.encode(text))
        except Exception:
            pass
    # Fallback: ~4 chars per token is a safe conservative estimate
    return len(text) // 4


def _truncate_context(context: str, max_tokens: int = _MAX_CONTEXT_TOKENS) -> Tuple[str, list]:
    """Truncate `context` to fit within `max_tokens`.

    Returns (truncated_context, warnings_list). When no truncation is needed
    the warnings_list is empty and the input is returned unchanged.

    Uses tiktoken for accurate token-boundary truncation when available;
    falls back to char-count slice (max_tokens * 4) on ImportError.
    """
    warnings: list = []
    if not context:
        return context, warnings

    current_tokens = _estimate_tokens(context)
    if current_tokens <= max_tokens:
        return context, warnings

    if _HAS_TIKTOKEN:
        try:
            encoder = tiktoken.get_encoding("cl100k_base")
            tokens = encoder.encode(context)
            context = encoder.decode(tokens[:max_tokens])
        except Exception:
            context = context[: max_tokens * 4]
    else:
        context = context[: max_tokens * 4]

    warnings.append(
        f"Context truncated from ~{current_tokens} to {max_tokens} tokens to prevent overflow."
    )
    return context, warnings


def _check_consultor_available() -> Tuple[bool, dict]:
    """Pre-flight check: is the consultor role configured and reachable?

    Returns (ok=True, {}) when the consultor can be invoked.
    Returns (ok=False, error_dict) with status="disabled" when:
      - cfg.consultor_model is empty (kill switch — feature turned off), OR
      - llm.is_available("consultor") is False (provider not configured /
        API key missing / circuit breaker open).
    """
    if not cfg.consultor_model:
        return False, {
            "status": "disabled",
            "error": "Consultor is disabled. Set CONSULTOR_MODEL in .env to enable.",
        }

    provider = cfg.model_registry.get("consultor", {}).get("provider", "unknown")
    if not llm.is_available("consultor"):
        return False, {
            "status": "disabled",
            "error": f"Provider for consultor role ('{provider}') is not available or not configured.",
            "provider": provider,
        }

    return True, {}


def _check_rate_limit() -> Tuple[bool, dict]:
    """Pre-flight check: is the consultor provider's rate-limit window clear?

    Returns (ok=True, {}) when the call is allowed.
    Returns (ok=False, error_dict) with status="rate_limited" when the
    sliding-window limiter denies the call.

    Uses the consultor role's provider name as the rate-limit key, matching
    the original consult.py behavior.
    """
    provider = cfg.model_registry.get("consultor", {}).get("provider", "unknown")
    if not check_rate_limit(provider):
        return False, {
            "status": "rate_limited",
            "error": f"Rate limit exceeded for {provider}. Please wait before consulting again.",
            "provider": provider,
        }
    return True, {}


def _get_consultor_provider() -> str:
    """Return the consultor role's provider name (or 'unknown' if misconfigured).

    Centralized so action handlers don't poke cfg.model_registry directly —
    this keeps cfg access in one place and makes mocking straightforward.
    """
    return cfg.model_registry.get("consultor", {}).get("provider", "unknown")


def _call_consultor(system: str, user: str, context: str = "", trace_id: str = ""):
    """Invoke llm.complete(role='consultor', ...).

    Centralized so action handlers don't reference `llm` directly. Tests that
    patch `tools.consult_ops.helpers.llm` transparently intercept this call —
    patching the module attribute works because this function looks up `llm`
    in the helpers module namespace at call time, NOT at import time.

    Returns the LLMResponse object from llm.complete() (real or mocked).
    """
    return llm.complete(
        role="consultor",
        system=system,
        user=user,
        context=context,
        trace_id=trace_id,
    )
