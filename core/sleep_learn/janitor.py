# core/sleep_learn/janitor.py
"""Handles purging of expired or low-confidence learned rules.

Uses the same singleton ChromaDB client pattern as storage.py and feedback.py
to avoid creating a new PersistentClient on every janitor run.
"""
from __future__ import annotations
import time
from core.sleep_learn.config import _SLEEP_LEARN_DB_PATH, SLEEP_LEARN_COLLECTION_NAME
from core.config import cfg

# [P3 FIX] Singleton ChromaDB client to prevent creating a new client
# on every janitor run. PersistentClient is expensive (opens SQLite +
# loads embedding model metadata). Consistent with storage.py/feedback.py.
_chroma_client = None
_chroma_collection = None

def _get_collection():
    """Lazy singleton: load ChromaDB client and collection once.
    
    v1.0 (Commit 4): when SLEEP_LEARN_UNIFIED=True, uses the main memory's
    procedural collection. purge_stale_rules now operates on the unified
    collection (folded into memory_backend/janitor.py conceptually, but
    the function stays here to preserve the Janitor Bypass pattern).
    """
    global _chroma_client, _chroma_collection
    if _chroma_collection is None:
        from core.sleep_learn.config import SLEEP_LEARN_UNIFIED
        if SLEEP_LEARN_UNIFIED:
            from core.memory_engine import memory
            _chroma_collection = memory._col("procedural")
        else:
            import chromadb
            _chroma_client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
            _chroma_collection = _chroma_client.get_or_create_collection(
                name=SLEEP_LEARN_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
    return _chroma_collection

def purge_stale_rules() -> dict:
    """Deletes rules older than cfg.purge_age_days or with confidence < 0.5."""
    stats = {"purged": 0, "error": None}
    try:
        col = _get_collection()

        all_data = col.get(include=["metadatas"])
        if not all_data["ids"]:
            return stats

        now = int(time.time())
        purge_age_secs = cfg.purge_age_days * 86400
        ids_to_delete = []

        for i, meta in enumerate(all_data["metadatas"]):
            created_at = meta.get("created_at", 0)
            confidence = meta.get("confidence_score", 1.0)

            # P0 Fix: Never purge rules that have been recalled (rare but critical)
            # Only purge if: (Old AND Never Used) OR (Confidence too low)
            recall_count = meta.get("recall_count", 0)
            # Conservative fallback: If never recalled, give it 180 days before purging
            is_stale = (now - created_at > max(purge_age_secs, 15552000)) and (recall_count == 0)

            if is_stale or (confidence < 0.5):
                ids_to_delete.append(all_data["ids"][i])

        if ids_to_delete:
            col.delete(ids=ids_to_delete)
            stats["purged"] = len(ids_to_delete)

    except Exception as e:
        stats["error"] = str(e)

    return stats
