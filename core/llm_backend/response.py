"""
core/llm_backend/response.py — Unified LLM response object + ToolCall.

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
v1.4: Added ToolCall dataclass + tool_calls field for native tool calling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class ToolCall:
    """A single tool call requested by the LLM (v1.4).

    Provider adapters convert their native format (OpenAI ``tool_calls``,
    Anthropic ``tool_use`` blocks, Gemini ``functionCall`` parts) into this
    unified shape. The ``complete_with_tools()`` loop only ever sees
    ``ToolCall`` objects — never provider-specific formats.

    Attributes:
        id: Provider-minted call ID (for round-tripping the result). Gemini
            doesn't mint IDs — the adapter generates position-based synthetic
            ones (``gemini_tc_0``, ``gemini_tc_1``).
        name: Tool name (e.g. ``"file"``, ``"web"``). For meta-tools, the
            specific action is in ``arguments["action"]``.
        arguments: Always a parsed dict (never a JSON string). For meta-tools,
            includes ``"action"`` + the action's params.
    """
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Unified response object returned by all LLM calls.

    v1.4: Added ``tool_calls`` field (empty list by default — backward
    compatible). Populated only by ``complete_with_tools()``; the existing
    ``complete()`` / ``call()`` / ``complete_provider()`` paths never set it
    (they go through ``_parse_response`` which ignores tool_calls in the raw
    response).
    """
    text:     str
    role:     str
    model:    str
    usage:    dict[str, int]
    elapsed:  float
    parsed:   Optional[Any]           = None
    error:    str                     = ""
    ok:       bool                    = True
    tool_calls: list[ToolCall]        = field(default_factory=list)
    # v1.4.1: Structured loop metadata (set by complete_with_tools()).
    # iterations: how many LLM calls the loop made (0 for single-turn paths).
    # reason: structured bail reason — "max_iterations", "consecutive_errors",
    #         "cancelled", "llm_error", or "" for success. Replaces fragile
    #         substring-matching on error text in callers (subagent).
    # v1.4.2: tool_calls is populated by _parse_response() whenever the LLM
    # response includes tool_calls (any provider). Existing callers (complete/
    # call/complete_provider) ignore it; complete_with_tools() consumes it.
    iterations: int                   = 0
    # v1.5: Literal type — catches typos at static-analysis time. Adding a
    # new reason is a 2-place edit (here + the dict in subagent._run_multi_turn_native).
    reason:    Literal["max_iterations", "consecutive_errors", "cancelled", "llm_error", ""] = ""

    @classmethod
    def from_error(cls, role: str, model: str, error: str, elapsed: float = 0.0) -> "LLMResponse":
        return cls(
            text="", role=role, model=model,
            usage={"prompt": 0, "completion": 0, "total": 0},
            elapsed=elapsed, error=error, ok=False,
        )
