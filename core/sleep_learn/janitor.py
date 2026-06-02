"""
core/sleep_learn/janitor.py
Handles purging of expired or low-confidence learned rules.
"""
from __future__ import annotations
import time
from core.sleep_learn.config import _SLEEP_LEARN_DB_PATH, SLEEP_LEARN_COLLECTION_NAME
from core.config import cfg

def purge_stale_rules() -> dict:
    """Deletes rules older than cfg.purge_age_days or with confidence < 0.5."""
    stats = {"purged": 0, "error": None}
    try:
        import chromadb  # LAZY IMPORT
        client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
        col = client.get_collection(SLEEP_LEARN_COLLECTION_NAME)
        
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
