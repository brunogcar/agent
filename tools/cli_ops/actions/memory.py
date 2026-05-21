"""
memory.py — Memory tool proxy for cli meta-tool.

Direct ChromaDB access via core/memory.py singleton.
Mirrors the memory() tool parameter names exactly.
"""

from __future__ import annotations

from typing import Any

def _mem():
    """Lazy import of ChromaDB store."""
    from core.memory import memory as _store
    return _store

def _memory(action: str, **kw: Any) -> str:
    """Proxy to memory store with formatted output."""
    store = _mem()

    try:
        if action == "recall":
            results = store.recall(
                query=kw.get("query", ""),
                top_k=kw.get("top_k", 5),
                collections=kw.get("collections"),
                min_score=kw.get("min_score", 0.5),
                tags_filter=kw.get("tags_filter", ""),
            )
            if not results:
                return "No memories found."
            return "\n".join(
                f"[{r.get('collection','?')}] score={r.get('score',0):.1f} | "
                f"{r.get('text', r.get('document',''))[:120]}..."
                for r in results[:5]
            )

        if action == "store":
            mem_type = kw.get("memory_type", "semantic")
            text = kw.get("text", "")
            importance = kw.get("importance", 5)
            tags = kw.get("tags", "")
            if mem_type == "episodic":
                store.store_episodic(
                    text, importance=importance,
                    goal=kw.get("goal",""), outcome=kw.get("outcome","unknown"),
                    tools_used=kw.get("tools_used",""), trace_id=kw.get("trace_id","")
                )
            elif mem_type == "procedural":
                store.store_procedural(text, importance=importance, tags=tags)
            else:
                store.store_semantic(text, importance=importance, tags=tags)
            return f"Stored ({mem_type}, importance={importance})."

        if action == "stats":
            stats = store.get_stats()
            return "\n".join(f"{col}: {cnt} entries" for col, cnt in stats.items())

        if action == "prune":
            removed = store.prune()
            return f"Pruned {removed} low-score memories."

        return f"Unknown memory action '{action}'. Use: recall | store | stats | prune"

    except Exception as e:
        return f"Memory error: {e}"