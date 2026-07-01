"""Tavily action: research — End-to-end deep research (workflow-only).

NOT registered in DISPATCH — not exposed as a tool action.
Workflows should import directly:
    from tools.tavily_ops.actions.research import run_research

v1.3 FIXES:
- Wire _run_async_with_resilience for CB + retry (was bypassing all resilience).
- Wire core/net/default constants.
- Wire budget tracking.
"""
from __future__ import annotations
from typing import Optional

from core.contracts import ok, fail
from core.net.budget import record_tool_call, check_budget
from tools.tavily_ops.errors import _handle_tavily_error
import tools.tavily_ops.client as _client
from tools.tavily_ops import bridge

# Valid citation formats per tavily-python SDK 0.7.26
_CITATION_FORMATS = ("numbered", "mla", "apa", "chicago")


def run_research(
    input: str = "",
    model: Optional[str] = None,
    citation_format: str = "apa",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """
    Execute Tavily research (end-to-end deep research).
    NOT exposed in the @tool facade — reserved for workflow use.

    v1.3: Now uses _run_async_with_resilience for circuit breaker + retry.
    """
    if _client._is_keyless():
        return fail(
            "research action requires a Tavily API key. "
            "Set TAVILY_API_KEY in .env.",
            trace_id=trace_id,
        )

    if citation_format not in _CITATION_FORMATS:
        return fail(
            f"citation_format must be one of {_CITATION_FORMATS}, got {citation_format!r}",
            trace_id=trace_id,
        )

    if not input:
        return fail("input is required for research action", trace_id=trace_id)

    # v1.3: Budget check
    if not check_budget("tavily.research"):
        return fail(
            "Tavily research budget exhausted. Try again tomorrow.",
            trace_id=trace_id,
            error_code="QUOTA_EXHAUSTED",
        )

    def _call():
        client = _client._get_singleton_client()
        return client.research(
            input=input,
            model=model,
            citation_format=citation_format,
        )

    try:
        # v1.3 FIX: Use _run_async_with_resilience instead of _run_async(_call())
        result = bridge._run_async_with_resilience(_call, trace_id=trace_id)
    except Exception as e:
        return _handle_tavily_error(e, trace_id=trace_id)

    # v1.3: Record successful API call
    record_tool_call("tavily.research")

    from core.memory_backend.pruner import prune_tool_dict

    response = ok(
        {
            "answer": result.get("answer", ""),
            "citations": result.get("citations", []),
            "keyless": False,
        },
        trace_id=trace_id,
    )
    return prune_tool_dict("tavily", response, trace_id)
