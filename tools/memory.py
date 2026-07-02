"""tools/memory.py — Memory meta-tool facade.

Exposes core/memory_engine.py to the LLM as a single @tool.
All logic lives in tools/memory_ops/actions/; this file is pure dispatch.

The LLM sees ONE tool: memory(action, ...)

Key design:
  - Lazy loading: ChromaDB is only loaded on first non-janitor call.
  - Janitor bypass: archive_old_episodes() + purge_stale_rules() run without
    touching the memory store (avoids ChromaDB import).
  - MED-05: Tag validation at tool layer before passing to backend.
  - Result compression: All responses pass through compress_result().
  - Trace ID threading: trace_id propagated through all action results.
"""
from __future__ import annotations

from registry import tool
from tools._meta_tool import meta_tool
from core.contracts import fail
from core.utils import compress_result

# Import action modules to trigger @register_action auto-discovery
from tools.memory_ops import DISPATCH  # noqa: F401


@tool
@meta_tool(
    DISPATCH.get("memory", {}),
    doc_sections=[
        "IMPORTANT — collections parameter:",
        '  collections — Filter to specific collections. Omit or pass None for all.',
        '  collections=[] is REJECTED (empty list is ambiguous).',
        "",
        "Memory types:",
        '  episodic — things that happened (task runs, outcomes)',
        '  semantic — things you know (facts, research, knowledge)',
        '  procedural — how to do things (fix patterns, solutions)',
        "",
        "Actions intentionally excluded from autonomous execution:",
        "  None — all 8 actions are safe for autonomous use.",
    ],
)
def memory(
    action: str,
    text: str = "",
    memory_type: str = "semantic",
    importance: int = 5,
    tags: str = "",
    trace_id: str = "",
    goal: str = "",
    outcome: str = "unknown",
    tools_used: str = "",
    source: str = "",
    query: str = "",
    top_k: int = 5,
    collections=None,
    min_score: float = 0.5,
    tags_filter: str = "",
    threshold: float = 0.0,
    confirm_ids=None,
    max_age_days: int = 30,
    min_importance: int = 3,
    dry_run: bool = True,
) -> dict:
    """Memory meta-tool — store, recall, and manage agent memories."""
    action = action.strip().lower() if action else ""

    if not action:
        return fail("action is required", trace_id=trace_id)

    dispatch = DISPATCH.get("memory", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
        )

    # Build kwargs from all parameters — handlers use **kwargs to absorb unused ones
    kwargs = {
        "text": text,
        "memory_type": memory_type,
        "importance": importance,
        "tags": tags,
        "trace_id": trace_id,
        "goal": goal,
        "outcome": outcome,
        "tools_used": tools_used,
        "source": source,
        "query": query,
        "top_k": top_k,
        "collections": collections,
        "min_score": min_score,
        "tags_filter": tags_filter,
        "threshold": threshold,
        "confirm_ids": confirm_ids,
        "max_age_days": max_age_days,
        "min_importance": min_importance,
        "dry_run": dry_run,
    }

    result = op_info["func"](**kwargs)

    if not isinstance(result, dict):
        return fail(
            f"Handler '{action}' returned {type(result).__name__}, expected dict",
            trace_id=trace_id,
        )

    # Thread trace_id through all results for observability
    if trace_id and "trace_id" not in result:
        result["trace_id"] = trace_id

    return compress_result(result)
