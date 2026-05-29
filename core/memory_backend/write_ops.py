"""
core/memory_backend/write_ops.py — Pure functions for memory write operations.
Implements O(1) Hash Guard, Contextual Feedback, and Procedural Reinforcement.
"""
from __future__ import annotations

import os
import time
import uuid

from core.config import cfg
from core.tracer import tracer
from core.memory_backend.constants import (
    COLLECTION_EPISODIC, COLLECTION_SEMANTIC, COLLECTION_PROCEDURAL,
    DEFAULT_DEDUP_THRESHOLDS, MAX_DUPLICATE_PREVIEW_CHARS
)
from core.memory_backend.scoring import normalize_and_hash


def _build_duplicate_payload(docs, distances, metas, ids, collection):
    """Helper to build consistent contextual feedback for both outer and inner dedup checks."""
    existing_text = docs[0]
    existing_id = ids[0] if ids else "unknown"
    
    snippet = existing_text[:MAX_DUPLICATE_PREVIEW_CHARS]
    if len(existing_text) > MAX_DUPLICATE_PREVIEW_CHARS:
        snippet += "..."
        
    return {
        "status": "skipped_duplicate",
        "reason": "semantic_match",
        "action": "reference_existing",
        "directive": "This knowledge is already in memory. Do not retry with overlapping chunks.",
        "matched_snippet": snippet,
        "existing_id": existing_id,
        "match_distance": round(distances[0], 4),
        "retry_recommended": False,
        "collection": collection
    }


def execute_store(
    store,          # The MemoryStore instance (passed explicitly)
    collection: str,
    text: str,
    importance: int = 5,
    tags: str = "",
    trace_id: str = "",
    goal: str = "",
    outcome: str = "unknown",
    tools_used: str = "",
    source: str = "",
) -> dict:
    """Internal store logic — shared by all three typed store methods."""
    
    # 🔴 Cancellation Guard: Abort before any memory mutations
    from core.cancellation import ensure_not_cancelled
    ensure_not_cancelled(trace_id)

    text_bytes = len(text.encode("utf-8"))
    if text_bytes > cfg.memory_max_entry_bytes:
        return {
            "status": "error",
            "error": (
                f"text is {text_bytes} bytes -- exceeds {cfg.memory_max_entry_bytes} byte limit. "
                "Summarise or chunk the content before storing."
            ),
        }

    importance = max(1, min(10, importance))
    col = store._col(collection)

    _dedup_thresh = float(
        os.getenv("MEMORY_DEDUP_THRESHOLD", "")
        or DEFAULT_DEDUP_THRESHOLDS.get(collection, 0.08)
    )

    # ==========================================
    # FIX B: O(1) Hash Guard (Exact Match) - OUTER CHECK
    # ==========================================
    text_hash = normalize_and_hash(text)
    if text_hash in store._hash_cache:
        return {
            "status": "skipped_duplicate",
            "reason": "exact_hash_match",
            "action": "reference_existing",
            "directive": "This exact text is already in memory. Do not retry.",
            "retry_recommended": False,
            "collection": collection
        }

    memory_id = str(uuid.uuid4())

    # ===== MED-01 FIX: Write-Only Lock pattern (Solution B) =====
    # Outer vector dedup (best effort, fast path)
    try:
        existing = col.query(
            query_texts=[text], 
            n_results=1,
            include=["documents", "distances", "metadatas"]
        )
        docs      = existing.get("documents", [[]])[0]
        distances = existing.get("distances", [[]])[0]
        
        if docs and distances and distances[0] < _dedup_thresh:
            # Fast path hit! Return contextual feedback. 
            # We skip reinforcement here to avoid the Read/Write race condition.
            metas = existing.get("metadatas", [[]])[0]
            ids   = existing.get("ids", [[]])[0]
            return _build_duplicate_payload(docs, distances, metas, ids, collection)
            
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        tracer.error(trace_id, "write_ops", f"Failed to fetch existing memories for dedup: {e}")

    # Lock only the actual insert operation - this is the critical section!
    with store._write_lock:
        # 🔴 TOCTOU fix: Re-check Hash and Vector inside the lock
        
        # 1. Re-check Hash Cache (Fixes Hash TOCTOU)
        if text_hash in store._hash_cache:
            return {
                "status": "skipped_duplicate",
                "reason": "exact_hash_match",
                "action": "reference_existing",
                "directive": "This exact text is already in memory. Do not retry.",
                "retry_recommended": False,
                "collection": collection
            }

        # 2. Re-check Vector (Fixes Inner Dedup Blind Spot & Reinforcement Race)
        try:
            existing_inner = col.query(
                query_texts=[text], 
                n_results=1, 
                include=["documents", "distances", "metadatas"]
            )
            inner_docs = existing_inner.get("documents", [[]])[0]
            inner_dists = existing_inner.get("distances", [[]])[0]
            
            if inner_docs and inner_dists and inner_dists[0] < _dedup_thresh:
                inner_metas = existing_inner.get("metadatas", [[]])[0]
                inner_ids   = existing_inner.get("ids", [[]])[0]
                
                # ==========================================
                # FIX C: Procedural Reinforcement (NOW INSIDE LOCK)
                # ==========================================
                if collection == COLLECTION_PROCEDURAL:
                    existing_meta = inner_metas[0] if inner_metas else {}
                    existing_id = inner_ids[0] if inner_ids else None
                    
                    if existing_id:
                        new_count = existing_meta.get("reinforcement_count", 0) + 1
                        existing_meta["reinforcement_count"] = new_count
                        existing_meta["last_reinforced"] = int(time.time())
                        
                        col.update(ids=[existing_id], metadatas=[existing_meta])
                        store._hash_cache.add(text_hash)
                        
                        return {
                            "status": "reinforced",
                            "reason": "semantic_match",
                            "existing_id": existing_id,
                            "reinforcement_count": new_count,
                            "collection": collection
                        }
                
                # If not procedural, return the contextual feedback (Fixes Inner Blind Spot)
                return _build_duplicate_payload(inner_docs, inner_dists, inner_metas, inner_ids, collection)
                
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            tracer.error(trace_id, "write_ops", f"Inner dedup check failed (non-fatal): {e}")
        
        # 3. Actual Insert
        try:
            col.add(documents=[text], ids=[memory_id], metadatas={
                "type":       collection,
                "importance": importance,
                "tags":       tags,
                "timestamp":  int(time.time()),
                "trace_id":   trace_id,
                "goal":       goal[:200],
                "outcome":    outcome,
                "tools_used": tools_used,
                "source":     source[:200],
                "text_hash":  text_hash,
                "reinforcement_count": 0,
                "last_reinforced": int(time.time()),
            })
            store._hash_cache.add(text_hash)
            return {"status": "stored", "id": memory_id, "collection": collection}
        except Exception as e:
            return {"status": "error", "error": str(e)}