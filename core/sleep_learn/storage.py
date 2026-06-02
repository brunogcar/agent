"""
core/sleep_learn/storage.py
Saves validated rules to a physically isolated ChromaDB collection.
GUARDRAIL: This module only WRITES. The daemon is forbidden from reading this.
"""
from __future__ import annotations
import time
import hashlib
import chromadb

from core.sleep_learn.config import (
    _SLEEP_LEARN_DB_PATH, 
    SLEEP_LEARN_COLLECTION_NAME
)

# Initialize isolated ChromaDB client
_client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
_collection = _client.get_or_create_collection(
    name=SLEEP_LEARN_COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)

def save_rule(rule_text: str, source_memory_id: str, confidence: float = 0.8) -> str:
    """
    Saves a validated rule to the isolated collection.
    Returns the generated rule_id.
    """
    # Generate a deterministic ID based on content to prevent exact duplicates
    rule_id = hashlib.sha256(rule_text.encode("utf-8")).hexdigest()[:16]
    
    # Check for exact duplicates before inserting
    existing = _collection.get(ids=[rule_id])
    if existing and existing['ids']:
        return rule_id  # Already exists, skip silently

    _collection.add(
        ids=[rule_id],
        documents=[rule_text],
        metadatas=[{
            "source_memory_id": source_memory_id,
            "confidence_score": confidence,
            "created_at": int(time.time()),
            "source": "sleep_learn_daemon",
            "phase": "2_active_distillation"
        }]
    )
    
    return rule_id

def get_collection_stats() -> dict:
    """Returns basic stats about the learned rules collection."""
    return {"count": _collection.count(), "name": SLEEP_LEARN_COLLECTION_NAME}
