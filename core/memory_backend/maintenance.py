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
            tracer.error("", "maintenance", f"ChromaDB query failed for collection {col_name}: {e}")
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
            tracer.error("", "maintenance", f"Failed to delete memory from collection {col_name}: {e}")
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
            tracer.error("", "maintenance", f"ChromaDB query failed for collection {col_name}: {e}")
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
            tracer.error("", "maintenance", f"Failed to delete memory from collection {col_name}: {e}")
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
            tracer.error("", "maintenance", f"ChromaDB query failed for collection {col_name}: {e}")
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
            tracer.error("", "maintenance", f"Failed to get count from collection {col_name}: {e}")
            result[col_name] = {"count": 0, "error": str(e)}
    return result

import math
import re

# Phase 6: Negation pattern for contradiction detection
NEGATION_PATTERN = re.compile(
    r"\b(never|don't|do not|avoid|instead of|stop|prevent|not\s+\w+|is not|are not|should not)\b", 
    re.IGNORECASE
)

def execute_diversity_maintenance(store, dry_run: bool = False) -> dict:
    """
    Phase 6: Memory Diversity Enforcement.
    Clusters procedural memories, merges near-duplicates, archives stale rules.
    """
    col = store._col(COLLECTION_PROCEDURAL)
    try:
        all_data = col.get(include=["metadatas", "documents"])
    except Exception as e:
        return {"status": "error", "error": str(e)}
        
    raw_ids = all_data.get("ids", [])
    raw_metas = all_data.get("metadatas", [])
    raw_docs = all_data.get("documents", [])
    
    if not raw_ids:
        return {"status": "success", "metrics": {"rules_processed": 0}}
        
    # Map IDs to their docs/metas for safe deterministic sorting
    data_map = {m_id: {"doc": doc, "meta": meta or {}} for m_id, doc, meta in zip(raw_ids, raw_docs, raw_metas)}
    ids = sorted(data_map.keys())
    
    processed = set()
    clusters = []
    
    # 1. Clustering (Greedy ChromaDB Walk)
    for mem_id in ids:
        if mem_id in processed:
            continue
            
        try:
            neighbors = col.query(
                query_texts=[data_map[mem_id]["doc"]],
                n_results=20,
                include=["metadatas", "documents", "distances"]
            )
        except Exception:
            continue
            
        n_ids = neighbors["ids"][0]
        n_dists = neighbors["distances"][0]
        n_metas = neighbors["metadatas"][0]
        n_docs = neighbors["documents"][0]
        
        cluster = []
        for j, n_id in enumerate(n_ids):
            if n_id in processed:
                continue
            if n_dists[j] <= cfg.diversity_distance_threshold:
                cluster.append({
                    "id": n_id,
                    "doc": n_docs[j],
                    "meta": n_metas[j] or {}
                })
                processed.add(n_id)
                
        if len(cluster) > 1:
            clusters.append(cluster)
            
    # 2. Merging & Contradiction Guard
    merges_performed = 0
    contradictions_detected = 0
    deleted_ids = set()
    
    with store._write_lock:
        for cluster in clusters:
            # Check for polarity inversions or mixed outcomes
            has_negation = [bool(NEGATION_PATTERN.search(c["doc"])) for c in cluster]
            outcomes = [c["meta"].get("outcome", "unknown") for c in cluster]
            
            if len(set(has_negation)) > 1 or len(set(outcomes)) > 1:
                contradictions_detected += 1
                if not dry_run:
                    flag_ids = [c["id"] for c in cluster]
                    flag_metas = [c["meta"] for c in cluster]
                    for m in flag_metas:
                        m["contradiction_flagged"] = True
                    try:
                        col.update(ids=flag_ids, metadatas=flag_metas)
                    except Exception:
                        pass
                continue
                
            # Champion Selection
            def score(c):
                return (c["meta"].get("reinforcement_count", 0) * 2) + c["meta"].get("recall_count", 0)
                
            cluster.sort(key=score, reverse=True)
            champion = cluster[0]
            losers = cluster[1:]
            
            if not dry_run:
                champ_meta = champion["meta"]
                loser_reinf = sum(l["meta"].get("reinforcement_count", 0) for l in losers)
                loser_recall = sum(l["meta"].get("recall_count", 0) for l in losers)
                
                # Logarithmic absorption: Add log of losers to champion's existing count
                champ_reinf = champ_meta.get("reinforcement_count", 0)
                champ_recall = champ_meta.get("recall_count", 0)
                
                new_reinf = champ_reinf + math.log10(1 + loser_reinf)
                new_recall = champ_recall + math.log10(1 + loser_recall)
                
                champ_meta["reinforcement_count"] = round(new_reinf, 4)
                champ_meta["recall_count"] = round(new_recall, 4)
                champ_meta["merged_from"] = [l["id"] for l in losers]
                
                try:
                    col.update(ids=[champion["id"]], metadatas=[champ_meta])
                except Exception:
                    continue
                    
                # Delete Losers & Sync Hash Cache
                loser_ids = [l["id"] for l in losers]
                try:
                    col.delete(ids=loser_ids)
                    deleted_ids.update(loser_ids)
                    # Sync hash cache ONLY after successful deletion
                    for l in losers:
                        h = l["meta"].get("text_hash")
                        if h:
                            store._hash_cache.discard(h)
                except Exception as e:
                    logger.warning(f"[Diversity] Failed to delete losers {loser_ids}: {e}")
                    
            merges_performed += 1
            
        # 3. Archival & Purging
        rules_archived = 0
        rules_purged = 0
        cutoff_archive = time.time() - (cfg.archive_age_days * 86400)
        cutoff_purge = time.time() - (cfg.purge_age_days * 86400)
        
        for i, mem_id in enumerate(ids):
            if mem_id in deleted_ids:
                continue
                
            meta = metas[i] or {}
            if meta.get("archived"):
                # Hard delete after 90 days
                if meta.get("archived_at", 0) < cutoff_purge:
                    if not dry_run:
                        try:
                            col.delete(ids=[mem_id])
                            h = meta.get("text_hash")
                            if h: store._hash_cache.discard(h)
                            rules_purged += 1
                        except Exception:
                            pass
                continue
                
            recall = meta.get("recall_count", 0)
            ts = meta.get("timestamp", 0)
            
            # Archive if never recalled and older than 30 days
            if recall < 0.1 and ts < cutoff_archive:
                if not dry_run:
                    meta["archived"] = True
                    meta["archived_at"] = time.time()
                    try:
                        col.update(ids=[mem_id], metadatas=[meta])
                        rules_archived += 1
                    except Exception:
                        pass
                        
    metrics = {
        "rules_processed": len(ids),
        "clusters_found": len(clusters),
        "merges_performed": merges_performed,
        "rules_archived": rules_archived,
        "rules_purged": rules_purged,
        "contradictions_detected": contradictions_detected,
        "dry_run": dry_run
    }
    
    return {"status": "success", "metrics": metrics}