"""
core/sleep_learn/storage.py
Saves validated rules to a physically isolated ChromaDB collection.
GUARDRAIL: This module only WRITES. The daemon is forbidden from reading this.
"""
from __future__ import annotations
import time
import hashlib
from typing import Dict, Any

from core.sleep_learn.config import (
    _SLEEP_LEARN_DB_PATH,
    SLEEP_LEARN_COLLECTION_NAME
)

# [P1 FIX] Singleton ChromaDB client to prevent creating a new client
# on every call. ChromaDB PersistentClient is expensive to instantiate
# (opens SQLite + loads embedding model metadata).
_chroma_client = None
_chroma_collection = None

def _get_collection():
    """Lazy singleton: load ChromaDB client and collection once.
    
    v1.0 (Commit 4): when SLEEP_LEARN_UNIFIED=True, writes go to the main
    memory's `procedural` collection instead of the isolated `procedural_meta`.
    """
    global _chroma_client, _chroma_collection
    if _chroma_collection is None:
        from core.sleep_learn.config import SLEEP_LEARN_UNIFIED
        if SLEEP_LEARN_UNIFIED:
            # Unified mode: use the main memory store's procedural collection
            from core.memory_engine import memory
            _chroma_collection = memory._col("procedural")
        else:
            # Legacy mode: isolated procedural_meta collection
            import chromadb
            _chroma_client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
            _chroma_collection = _chroma_client.get_or_create_collection(
                name=SLEEP_LEARN_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
    return _chroma_collection

def save_rule(rule_text: str, source_memory_id: str, confidence: float = 0.8) -> str:
    """
    Saves a validated rule to the isolated collection.
    Returns the generated rule_id.
    """
    rule_id = hashlib.sha256(rule_text.encode("utf-8")).hexdigest()[:16]
    collection = _get_collection()

    # Check for exact duplicates before inserting
    existing = collection.get(ids=[rule_id])
    if existing and existing['ids']:
        return rule_id  # Already exists, skip silently

    # v1.0: Use the unified rule schema (core/memory_backend/rule_schema.py)
    # This aligns sleep_learn's output with the L3 contract so the migration
    # (Commit 4) can move rules into the unified `procedural` collection
    # without schema conversion.
    from core.memory_backend.rule_schema import build_unified_metadata
    import time as _time
    now = int(_time.time())
    unified_meta = build_unified_metadata(
        text=rule_text,
        source="sleep_learn",
        confidence=confidence,
        source_memory_id=source_memory_id,
        created_at=now,
        last_accessed_at=now,
        recall_count=0,
        reasoning="",  # Commit 3's reasoning field — populated by the distiller in a future commit
    )
    # Also keep confidence_score for backward compat with the injector's
    # where={"confidence_score": {"$gte": ...}} filter (until Commit 4 migration)
    unified_meta["confidence_score"] = confidence
    unified_meta["phase"] = "2_active_distillation"  # kept for backward compat
    
    collection.add(
        ids=[rule_id],
        documents=[rule_text],
        metadatas=[unified_meta]
    )

    return rule_id

def get_collection_stats() -> dict:
    """Returns basic stats about the learned rules collection."""
    collection = _get_collection()
    return {"count": collection.count(), "name": SLEEP_LEARN_COLLECTION_NAME}
