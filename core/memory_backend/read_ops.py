"""
core/memory_backend/read_ops.py — Pure functions for memory read operations.
"""
from __future__ import annotations

import time

from core.config import cfg
from core.tracer import tracer
from core.memory_backend.constants import ALL_COLLECTIONS
from core.memory_backend.scoring import _decay_score, _rewrite_query


def execute_recall(
    store,
    query: str,
    top_k: int = None,
    collections: list[str] = None,
    min_score: float = 0.5,
    tags_filter: str = "",
    trace_id: str = "",
) -> list[dict]:
    """Recall memories semantically similar to query."""
    top_k       = top_k or cfg.memory_top_k
    collections = collections or ALL_COLLECTIONS

    rewritten = _rewrite_query(query)
    if trace_id:
        tracer.step(trace_id, "memory_recall", original=query[:60], rewritten=rewritten[:60])

    fetch_multiplier = max(2, 5 - top_k // 5)
    fetch_k = max(top_k * fetch_multiplier, 15)
    results   = []

    for col_name in collections:
        if col_name not in ALL_COLLECTIONS:
            continue
        col = store._col(col_name)

        try:
            raw = col.query(
                query_texts=[rewritten],
                n_results=min(fetch_k, col.count() or 1),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            tracer.error(trace_id, "read_ops", f"ChromaDB query failed for collection {col_name}: {e}")
            continue

        docs      = raw.get("documents", [[]])[0]
        metas     = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            importance = meta.get("importance", 5)
            timestamp  = meta.get("timestamp", 0)
            tags       = meta.get("tags", "")
            reinf      = meta.get("reinforcement_count", 0)
            
            # Uses the new scoring function with decay bypass & reinforcement
            score      = _decay_score(importance, timestamp, col_name, reinf)
            age_days   = round((time.time() - timestamp) / 86400, 1)

            if score < min_score:
                continue
            if tags_filter:
                wanted = {t.strip() for t in tags_filter.split(",")}
                actual = {t.strip() for t in tags.split(",")}
                if not wanted & actual:
                    continue

            results.append({
                "text":       doc,
                "type":       col_name,
                "importance": importance,
                "score":      score,
                "distance":   round(dist, 4),
                "tags":       tags,
                "goal":       meta.get("goal", ""),
                "outcome":    meta.get("outcome", ""),
                "tools_used": meta.get("tools_used", ""),
                "source":     meta.get("source", ""),
                "trace_id":   meta.get("trace_id", ""),
                "age_days":   age_days,
                "collection": col_name,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    final = results[:top_k]

    if trace_id:
        tracer.step(trace_id, "memory_recall_done", results=len(final), collections=collections)

    return final


def execute_recall_context(
    store,
    query: str,
    top_k: int = None,
    collections: list[str] = None,
    trace_id: str = "",
) -> str:
    """Convenience wrapper — returns a formatted context string."""
    results = execute_recall(store, query, top_k, collections, trace_id=trace_id)
    if not results:
        return ""

    lines = []
    for r in results:
        prefix = f"[{r['type']} | score={r['score']} | {r['age_days']}d ago] "
        lines.append(f"{prefix} {r['text']}")

    return "\n".join(lines)