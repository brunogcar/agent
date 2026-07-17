"""tools/memory.py — Memory meta-tool facade.
Pure dispatch: no logic, no _mem() call. All work delegated to action handlers.
v1.2: compress_result wrapped in try/except, duration_ms added, dead import removed.
"""
from __future__ import annotations

import time

from core.utils import compress_result
from core.contracts import fail
from tools._meta_tool import meta_tool
from registry import tool

# Import action modules to trigger @register_action auto-discovery
from tools.memory_ops import DISPATCH  # noqa: F401

@tool
@meta_tool(
    DISPATCH.get("memory", {}),
    doc_sections=[
        "IMPORTANT — collections parameter:",
        "  collections — Filter to specific collections. Omit or pass None for all.",
        "  collections=[] is REJECTED (empty list is ambiguous).",
        "",
        "Memory types:",
        "  episodic — things that happened (task runs, outcomes)",
        "  semantic — things you know (facts, research, knowledge)",
        "  procedural — how to do things (fix patterns, solutions)",
        "",
        "Actions requiring human confirmation in autonomous contexts:",
        "  delete — permanent data loss",
        "  prune — permanent data loss when dry_run=False",
        "  All other actions are safe for autonomous use.",
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
    # v1.3 — Chunking (store action only; ignored by all other actions)
    chunk: bool = False,
    chunk_method: str = "token",
    chunk_size: int = 512,
    # v1.4 — update / export / import / group-delete params
    fields: dict = None,
    reason: str = "",
    id: str = "",
    source_doc_id: str = "",
    input_path: str = "",
    output_path: str = "",
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
        # v1.3 chunking params — always passed; only the store action uses them
        "chunk": chunk,
        "chunk_method": chunk_method,
        "chunk_size": chunk_size,
        # v1.4 — new action params
        "fields": fields,
        "reason": reason,
        "id": id,
        "source_doc_id": source_doc_id,
        "input_path": input_path,
        "output_path": output_path,
    }

    start = time.time()
    try:
        result = op_info["func"](**kwargs)
    except Exception as e:
        return fail(f"Handler '{action}' failed: {e}", trace_id=trace_id)

    if not isinstance(result, dict):
        return fail(
            f"Handler '{action}' returned {type(result).__name__}, expected dict",
            trace_id=trace_id,
        )

    if trace_id and "trace_id" not in result:
        result["trace_id"] = trace_id

    if result.get("status") == "success":
        try:
            result = compress_result(result)
        except Exception as e:
            return fail(f"Result compression failed: {e}", trace_id=trace_id)

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
