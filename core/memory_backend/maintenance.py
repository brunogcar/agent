"""
core/memory_backend/maintenance.py — Pure functions for memory maintenance.
Includes delete, prune, summarize, and stats.
"""
from __future__ import annotations

import time

from core.config import cfg
from core.tracer import tracer
from core.memory_backend.constants import (
    COLLECTION_EPISODIC, COLLECTION_SEMANTIC, COLLECTION_PROCEDURAL,
    ALL_COLLECTIONS
)
from core.memory_backend.scoring import _decay_score, _rewrite_query


def execute_delete(store, query: str, collections: list[str] = None, threshold: float = None, confirm_ids: list[str] = None) -> dict:
    """
    Delete memories within similarity threshold of query.
    Always returns what was found and what was deleted so the caller
    can show a dry-run preview before confirming.
    """
    threshold   = threshold or cfg.memory_delete_threshold
    collections = collections or ALL_COLLECTIONS
    rewritten   = _rewrite_query(query)

    candidates = []
    for col_name in collections:
        col = store._col(col_name)
        try:
            raw = col.query(
                query_texts=[rewritten],
                n_results=10,
                include=["documents", "metadatas", "distances"],
            )
            ids       = raw.get("ids", [[]])[0]
            docs      = raw.get("documents", [[]])[0]
            distances = raw.get("distances", [[]])[0]
            metas     = raw.get("metadatas", [[]])[0]

            for id_, doc, dist, meta in zip(ids, docs, distances, metas):
                if dist <= threshold:
                    candidates.append({
                        "id":         id_,
                        "text":       doc[:100],
                        "distance":   round(dist, 4),
                        "collection": col_name,
                        "_hash":      meta.get("text_hash"),  # For cache cleanup
                    })
        except Exception as e:
            tracer.error(f"ChromaDB query failed for collection {col_name}: {e}")
            continue

    if not candidates:
        return {"status": "no_match", "candidates": []}

    to_delete = candidates
    if confirm_ids:
        to_delete = [c for c in candidates if c["id"] in confirm_ids]

    if not to_delete:
        return {
            "status":      "awaiting_confirmation",
            "candidates": candidates,
            "note":        "Pass confirm_ids to confirm deletion",
        }

    by_col: dict[str, list[str]] = {}
    for c in to_delete:
        by_col.setdefault(c["collection"], []).append(c["id"])
        # Keep the O(1) Hash Guard in sync
        if c.get("_hash"):
            store._hash_cache.discard(c["_hash"])

    deleted = 0
    for col_name, ids in by_col.items():
        try:
            store._col(col_name).delete(ids=ids)
            deleted += len(ids)
        except Exception as e:
            tracer.error(f"Failed to delete memory from collection {col_name}: {e}")
            pass

    # Strip internal _hash key before returning to LLM/User
    clean_deleted = [{k: v for k, v in c.items() if k != "_hash"} for c in to_delete]

    return {
        "status":   "deleted",
        "count":   deleted,
        "deleted": clean_deleted,
    }


def execute_prune(store, max_age_days: int = 30, min_importance: int = 3, dry_run: bool = True, collections: list[str] = None) -> dict:
    """
    Remove old, low-importance memories.
    Protected from pruning:
    - Procedural collection (unless explicitly targeted)
    - anything tagged "summary", "critical", or "protected"
    - importance >= min_importance
    """
    collections = collections or [COLLECTION_EPISODIC, COLLECTION_SEMANTIC]
    if COLLECTION_PROCEDURAL in collections:
        collections = [c for c in collections if c != COLLECTION_PROCEDURAL]

    cutoff     = int(time.time()) - (max_age_days * 86400)
    candidates = []

    for col_name in collections:
        col = store._col(col_name)
        try:
            data  = col.get(include=["documents", "metadatas"])
            ids   = data.get("ids", [])
            docs  = data.get("documents", [])
            metas = data.get("metadatas", [])
        except Exception as e:
            tracer.error(f"ChromaDB query failed for collection {col_name}: {e}")
            continue

        for id_, doc, meta in zip(ids, docs, metas):
            importance = meta.get("importance", 5)
            timestamp  = meta.get("timestamp", 0)
            tags       = meta.get("tags", "")

            protected = any(t in tags for t in ["summary", "critical", "protected"])
            if protected or importance >= min_importance or timestamp > cutoff:
                continue

            age_days = round((time.time() - timestamp) / 86400, 1)
            candidates.append({
                "id":         id_,
                "text":       doc[:80] + ("..." if len(doc) > 80 else ""),
                "importance": importance,
                "age_days":   age_days,
                "collection": col_name,
                "_hash":      meta.get("text_hash"),
            })

    if not candidates:
        return {"status": "nothing_to_prune", "dry_run": dry_run}

    if dry_run:
        clean_candidates = [{k: v for k, v in c.items() if k != "_hash"} for c in candidates]
        return {
            "status":      "dry_run",
            "would_delete": len(candidates),
            "candidates":  clean_candidates,
            "note":        "Call again with dry_run=False to confirm",
        }

    by_col: dict[str, list[str]] = {}
    for c in candidates:
        by_col.setdefault(c["collection"], []).append(c["id"])
        if c.get("_hash"):
            store._hash_cache.discard(c["_hash"])

    deleted = 0
    for col_name, ids in by_col.items():
        try:
            store._col(col_name).delete(ids=ids)
            deleted += len(ids)
        except Exception as e:
            tracer.error(f"Failed to delete memory from collection {col_name}: {e}")
            pass

    clean_entries = [{k: v for k, v in c.items() if k != "_hash"} for c in candidates]
    return {"status": "pruned", "deleted": deleted, "entries": clean_entries}


def execute_summarize(store, collections: list[str] = None, top_n: int = 30, store_result: bool = True, trace_id: str = "") -> dict:
    """
    Summarize stored memories using the planner model.
    Stores the summary as a high-importance semantic memory.
    """
    from core.llm import llm

    collections = collections or ALL_COLLECTIONS
    all_docs    = []

    for col_name in collections:
        col = store._col(col_name)
        try:
            data = col.get(include=["documents", "metadatas"])
            docs  = data.get("documents", [])
            metas = data.get("metadatas", [])
            for doc, meta in zip(docs, metas):
                all_docs.append({
                    "text":       doc,
                    "importance": meta.get("importance", 5),
                    "type":       col_name,
                    "timestamp":  meta.get("timestamp", 0),
                    "reinf":      meta.get("reinforcement_count", 0),
                })
        except Exception as e:
            tracer.error(f"ChromaDB query failed for collection {col_name}: {e}")
            continue

    if len(all_docs) < 3:
        return {"status": "not_enough_data", "count": len(all_docs)}

    # Sort by decay score (uses the new scoring function with reinforcement)
    for d in all_docs:
        d["_score"] = _decay_score(d["importance"], d["timestamp"], d["type"], d["reinf"])
        
    all_docs.sort(key=lambda x: x["_score"], reverse=True)
    top = all_docs[:top_n]

    combined = "\n".join(
        f"[{d['type']}|imp={d['importance']}] {d['text']}"
        for d in top
    )

    result = llm.complete(
        role   = "planner",
        system = (
            "You are a memory consolidation assistant. "
            "Given a list of agent memories, write a concise dense summary "
            "capturing: key facts, important patterns, critical fixes learned, "
            "and active goals. Output only the summary, no preamble."
        ),
        user    = "Summarize these agent memories:",
        content = combined,
        trace_id= trace_id,
    )

    if not result.ok:
        return {"status": "error", "error": result.error}

    summary_text = result.text

    if store_result:
        store.store_semantic(
            text       = f"MEMORY SUMMARY: {summary_text}",
            importance = 10,
            tags       = "summary,auto",
            trace_id   = trace_id,
        )

    return {
        "status":     "summarized",
        "summary":   summary_text,
        "input_count": len(top),
    }


def execute_stats(store) -> dict:
    """Return counts and basic stats for each collection."""
    result = {}
    for col_name in ALL_COLLECTIONS:
        col = store._col(col_name)
        try:
            count = col.count()
            result[col_name] = {"count": count}
        except Exception as e:
            tracer.error(f"Failed to get count from collection {col_name}: {e}")
            result[col_name] = {"count": 0, "error": str(e)}
    return result