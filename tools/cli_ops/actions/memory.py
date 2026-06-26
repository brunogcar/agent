"""Memory tool proxy for cli meta-tool.

Direct ChromaDB access via core/memory.py singleton.
All functions auto-register via @register_action decorator.
"""
from __future__ import annotations

from typing import Any

from tools.cli_ops._registry import register_action


def _mem():
    """Lazy import of ChromaDB store."""
    from core.memory import memory as _store
    return _store


@register_action(
    "memory", "recall",
    help_text="Recall memories from ChromaDB (shortcut: 'recall <query>').",
    examples=["recall my query"],
)
def _memory_recall(
    action: str = "",
    query: str = "",
    top_k: int = 5,
    collections: list = None,
    min_score: float = 0.5,
    tags_filter: str = "",
    **params,
) -> str:
    """Recall memories from ChromaDB."""
    store = _mem()
    try:
        results = store.recall(
            query=query,
            top_k=top_k,
            collections=collections,
            min_score=min_score,
            tags_filter=tags_filter,
        )
        if not results:
            return "No memories found."
        lines = []
        for r in results[:5]:
            col = r.get("collection", "?")
            score = r.get("score", 0)
            text = r.get("text", r.get("document", ""))[:120]
            lines.append(f"[{col}] score={score:.1f} | {text}...")
        return "\n".join(lines)
    except Exception as e:
        return f"Memory error: {e}"


@register_action(
    "memory", "store",
    help_text="Store memory in ChromaDB (shortcut: 'store <text>').",
    examples=["store my text"],
)
def _memory_store(
    action: str = "",
    text: str = "",
    memory_type: str = "semantic",
    importance: int = 5,
    tags: str = "",
    goal: str = "",
    outcome: str = "unknown",
    tools_used: str = "",
    trace_id: str = "",
    **params,
) -> str:
    """Store memory in ChromaDB."""
    store = _mem()
    try:
        if memory_type == "episodic":
            store.store_episodic(
                text, importance=importance, goal=goal,
                outcome=outcome, tools_used=tools_used, trace_id=trace_id,
            )
        elif memory_type == "procedural":
            store.store_procedural(text, importance=importance, tags=tags)
        else:
            store.store_semantic(text, importance=importance, tags=tags)
        return f"Stored ({memory_type}, importance={importance})."
    except Exception as e:
        return f"Memory error: {e}"


@register_action(
    "memory", "stats",
    help_text="Get memory statistics (shortcut: 'memory stats').",
    examples=["memory stats"],
)
def _memory_stats(action: str = "", **params) -> str:
    """Get memory statistics."""
    store = _mem()
    try:
        stats = store.stats()
        return "\n".join(f"{col}: {cnt} entries" for col, cnt in stats.items())
    except Exception as e:
        return f"Memory error: {e}"


@register_action(
    "memory", "prune",
    help_text="Prune low-score memories (shortcut: 'memory prune').",
    examples=["memory prune"],
)
def _memory_prune(action: str = "", **params) -> str:
    """Prune low-score memories."""
    store = _mem()
    try:
        removed = store.prune()
        return f"Pruned {removed} low-score memories."
    except Exception as e:
        return f"Memory error: {e}"
