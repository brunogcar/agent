"""
core/memory_backend/write_ops.py — Pure functions for memory write operations.
Implements O(1) Hash Guard, Contextual Feedback, and Procedural Reinforcement.

[DESIGN] KEY DECISIONS — read before modifying:

  1. TOCTOU RACE FIX: double-checked locking with TWO dedup checks.
     OUTER check (outside _write_lock): fast path, filters ~80% of duplicates.
     INNER check (inside _write_lock): authoritative — re-verifies BEFORE ChromaDB insert.
     DO NOT remove either check. DO NOT move the inner check outside the lock.

  2. execute_store() returns a RAW DICT, not wrapped in ok()/fail().
     Success: {"status": "stored", "id": memory_id, "collection": collection}
     Error:   {"status": "error", "error": str(e)}
     trace_id is NOT included. The tool layer wraps with ok(result, trace_id=...).

  3. _write_lock is per-MemoryStore instance, NOT module-level.
     Two MemoryStore instances have separate locks and do NOT protect each other.
     ALWAYS use the singleton from core/memory_engine.py.
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
    from core.runtime.cancellation import ensure_not_cancelled
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


# ═══════════════════════════════════════════════════════════════════════════════
# v1.1 — CHUNKED STORE
# ═══════════════════════════════════════════════════════════════════════════════
#
# WHY THIS EXISTS:
#   The standard execute_store() runs two-layer dedup (hash + vector) on every
#   store call. When storing a long document as N chunks, chunks from the same
#   document are semantically similar and would trigger vector dedup — chunk #2
#   gets skipped as a "duplicate" of chunk #1, chunk #3 skipped as a duplicate
#   of #2, etc. The document would be silently truncated to 1 chunk.
#
#   execute_store_chunked() solves this by:
#     1. Skipping vector dedup entirely (hash dedup only — chunks have different
#        text, so different hashes, so they all pass).
#     2. Batch-inserting all chunks in a single col.add() call (atomic + fast).
#     3. Linking chunks with a shared source_doc_id UUID + chunk_index metadata.
#
# WHAT THIS DOES NOT DO:
#   - Does NOT run on the procedural collection (procedural reinforcement is
#     nonsensical for chunks — which chunk gets reinforced?). The tool layer
#     rejects chunk=True on procedural before reaching this function.
#   - Does NOT run vector dedup against EXISTING memories. If a chunk happens
#     to be a near-duplicate of an existing memory from a different document,
#     both will coexist. This is an acceptable tradeoff — chunked documents are
#     meant to be granular, and the maintenance ops (prune, diversity enforcer)
#     handle cross-document cleanup separately.
#
# CALLERS:
#   - store.store_chunked() → this function
#   - tools/memory_ops/actions/store.py (when chunk=True) → store.store_chunked()
#
# SEE ALSO:
#   - docs/core/memory/API.md → "store_chunked()" section
#   - docs/core/memory/CHANGELOG.md → v1.1 entry
#   - docs/tools/memory/CHANGELOG.md → v1.3 entry
# ═══════════════════════════════════════════════════════════════════════════════

def execute_store_chunked(
    store,          # The MemoryStore instance (passed explicitly)
    collection: str,
    chunks: list[str],
    importance: int = 5,
    tags: str = "",
    trace_id: str = "",
    goal: str = "",
    outcome: str = "unknown",
    tools_used: str = "",
    source: str = "",
) -> dict:
    """Store a list of text chunks as linked memories in a single batch.

    All chunks share a `source_doc_id` (UUID) and carry `chunk_index` /
    `chunk_count` metadata so recall can identify them as fragments of a
    larger document.

    Dedup: hash-only (exact match). Vector dedup is deliberately skipped
    because chunks from the same document are semantically similar and would
    falsely trigger the vector dedup pipeline in execute_store().

    Returns:
        {"status": "stored", "source_doc_id": str, "stored": int,
         "skipped_duplicates": int, "chunk_count": int, "collection": str}
    """
    # 🔴 Cancellation Guard: Abort before any memory mutations
    from core.runtime.cancellation import ensure_not_cancelled
    ensure_not_cancelled(trace_id)

    if not chunks:
        return {"status": "error", "error": "chunks list is empty"}

    importance = max(1, min(10, importance))
    col = store._col(collection)

    # Generate a shared UUID for all chunks from this document.
    # This is the linker field — recall returns it so the LLM knows
    # a result is a fragment, not a complete memory.
    source_doc_id = str(uuid.uuid4())
    chunk_count = len(chunks)

    # ── Hash dedup (exact match only) ──────────────────────────────────────
    # We skip vector dedup entirely. See the block comment above for rationale.
    # Chunks with the exact same text as an existing memory (or as each other)
    # are skipped; everything else is batch-inserted.
    #
    # NOTE: We track batch_hashes separately from store._hash_cache because
    # hashes from THIS batch aren't in _hash_cache yet (they're added only
    # after col.add() succeeds). Without batch_hashes, duplicate chunks WITHIN
    # the same batch would both pass the _hash_cache check and both get stored.
    batch_hashes = set()  # intra-batch dedup — catches duplicate chunks in the same document
    now = int(time.time())
    docs_to_add = []
    ids_to_add = []
    metas_to_add = []
    skipped = 0

    for idx, chunk_text in enumerate(chunks):
        if not chunk_text or not chunk_text.strip():
            skipped += 1
            continue

        text_hash = normalize_and_hash(chunk_text)

        # O(1) hash guard — skip exact matches (existing memory OR earlier chunk in this batch)
        if text_hash in store._hash_cache or text_hash in batch_hashes:
            skipped += 1
            continue

        batch_hashes.add(text_hash)
        docs_to_add.append(chunk_text)
        ids_to_add.append(str(uuid.uuid4()))
        metas_to_add.append({
            "type":       collection,
            "importance": importance,
            "tags":       tags,
            "timestamp":  now,
            "trace_id":   trace_id,
            "goal":       goal[:200],
            "outcome":    outcome,
            "tools_used": tools_used,
            "source":     source[:200],
            "text_hash":  text_hash,
            "reinforcement_count": 0,
            "last_reinforced": now,
            # ── v1.1 chunking metadata ──────────────────────────────────
            # source_doc_id: UUID linking all chunks from the same document.
            #                Empty string "" for non-chunked memories (default).
            # chunk_index:   0-based position within the document.
            # chunk_count:   Total chunks in the document (≥1 for chunked, 0 for non-chunked).
            "source_doc_id": source_doc_id,
            "chunk_index":   idx,
            "chunk_count":   chunk_count,
        })

    if not docs_to_add:
        # All chunks were duplicates or empty
        return {
            "status": "skipped_duplicate",
            "reason": "all_chunks_duplicate_or_empty",
            "source_doc_id": source_doc_id,
            "stored": 0,
            "skipped_duplicates": skipped,
            "chunk_count": chunk_count,
            "collection": collection,
        }

    # ── Batch insert (atomic) ──────────────────────────────────────────────
    # Single col.add() call — faster than N individual calls and avoids
    # TOCTOU races between chunks of the same document.
    with store._write_lock:
        # Re-check hashes inside the lock (TOCTOU guard — same pattern as
        # execute_store, but only for hash dedup, not vector dedup).
        final_docs = []
        final_ids = []
        final_metas = []
        for doc, mid, meta in zip(docs_to_add, ids_to_add, metas_to_add):
            if meta["text_hash"] in store._hash_cache:
                skipped += 1
                continue
            final_docs.append(doc)
            final_ids.append(mid)
            final_metas.append(meta)

        if not final_docs:
            return {
                "status": "skipped_duplicate",
                "reason": "all_chunks_duplicate_or_empty",
                "source_doc_id": source_doc_id,
                "stored": 0,
                "skipped_duplicates": skipped,
                "chunk_count": chunk_count,
                "collection": collection,
            }

        try:
            col.add(
                documents=final_docs,
                ids=final_ids,
                metadatas=final_metas,
            )
            # Add all hashes to cache after successful insert
            for meta in final_metas:
                store._hash_cache.add(meta["text_hash"])

            return {
                "status": "stored",
                "source_doc_id": source_doc_id,
                "stored": len(final_docs),
                "skipped_duplicates": skipped,
                "chunk_count": chunk_count,
                "collection": collection,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}