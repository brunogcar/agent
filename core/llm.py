"""
core/llm.py - Unified LLM client with provider abstraction.

Design goals:
- Single call site for ALL model interactions - nothing else calls requests directly
- Provider abstraction from day one - adding DeepSeek/Claude/Groq later
  requires only a new Provider class, zero changes to callers
- Role-based dispatch - callers say "executor" not the raw model string from .env
- Per-role timeouts enforced here, not scattered across tool files
- Structured output support - request JSON, get a parsed dict back
- Full trace integration - every call logged with trace_id

BUG FIX: DeepSeek analysis applied 2026-05-14 (see git commit message for details):
- close_clients() broken AttributeError ? Fixed: singleton client pattern
- _make_client timeout no-op ? Fixed: concurrent.futures implementation
- CircuitBreaker HALF_OPEN state gaps ? Fixed: proper state transitions

EXTRACTION NOTE (LLM Phase 1):
This file is now a Thin Facade. All implementation logic (providers, client,
circuit breakers, role configs) has been extracted into core/llm_backend/.

Usage:
    from core.llm import llm
    result = llm.complete(
        role   = "executor",
        system = "You are a senior Python developer...",
        user   = "Fix this bug: ...",
    )
    text = result.text   # str
    ok   = result.ok     # bool
"""
from __future__ import annotations

import atexit

# -- Thin Facade -------------------------------------------------------------
from core.llm_backend.factory import create_llm_client
from core.llm_backend.client import LLMClient
from core.llm_backend.response import LLMResponse, ToolCall
from core.llm_backend.tools import ToolDefinition, tool_def_from_meta_tool, tool_def_from_registry
from core.llm_backend.circuit_breaker import CircuitBreaker
from core.llm_backend.providers.lmstudio import LMStudioProvider
from core.llm_backend.provider import ProviderRegistry, BaseProvider

llm = create_llm_client()

# -- Cleanup registration ----------------------------------------------------
# DeepSeek fix 2026-05-14: Proper atexit cleanup via llm singleton (not class method)
def _cleanup():
    """Close all registered provider clients."""
    for provider in llm._registry._providers.values():
        if hasattr(provider, 'close'):
            provider.close()

import atexit; atexit.register(_cleanup)