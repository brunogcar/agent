"""
core/memory_backend/store.py — The MemoryStore Thin Orchestrator.
Holds the Singleton state, thread locks, and delegates to pure functions.
"""
from __future__ import annotations

import threading

from core.memory_backend.constants import (
    COLLECTION_EPISODIC, COLLECTION_SEMANTIC, COLLECTION_PROCEDURAL,
    ALL_COLLECTIONS
)
from core.memory_backend.client import get_client as _make_client
from core.memory_backend.scoring import normalize_and_hash

import core.memory_backend.write_ops as write_ops
import core.memory_backend.read_ops as read_ops


class MemoryStore:
    """
    Three-collection ChromaDB memory store.
    Thin Orchestrator pattern: Holds state and delegates to pure functions.
    """
    def __init__(self) -> None:
        # FastAPI Reload Guard
        if hasattr(self, "_initialized"):
            return

        self._write_lock  = threading.Lock()  # guards concurrent writes
        self._client      = _make_client()
        self._collections = {
            name: self._client.get_or_create_collection(name)
            for name in ALL_COLLECTIONS
        }
        
        # O(1) Hash Guard
        self._hash_cache = set()
        self._load_hash_cache()
        
        self._initialized = True

    def _load_hash_cache(self):
        """Rebuild in-memory hash set on startup for O(1) dedup."""
        for col_name in ALL_COLLECTIONS:
            col = self._collections[col_name]
            try:
                data = col.get(include=["metadatas"])
                for meta in data.get("metadatas", []):
                    h = meta.get("text_hash")
                    if h:
                        self._hash_cache.add(h)
            except Exception:
                pass  # Non-fatal

    def _col(self, name: str):
        return self._collections[name]

    # ── Store Delegators ──────────────────────────────────────────────────

    def _store(self, collection: str, text: str, importance: int = 5, tags: str = "", trace_id: str = "", goal: str = "", outcome: str = "unknown", tools_used: str = "", source: str = "") -> dict:
        return write_ops.execute_store(self, collection, text, importance, tags, trace_id, goal, outcome, tools_used, source)

    def store_episodic(self, text: str, importance: int = 5, tags: str = "", trace_id: str = "", goal: str = "", outcome: str = "unknown", tools_used: str = "") -> dict:
        return self._store(COLLECTION_EPISODIC, text, importance, tags, trace_id, goal, outcome, tools_used)

    def store_semantic(self, text: str, importance: int = 5, tags: str = "", trace_id: str = "", source: str = "") -> dict:
        return self._store(COLLECTION_SEMANTIC, text, importance, tags, trace_id, source=source)

    def store_procedural(self, text: str, importance: int = 7, tags: str = "", trace_id: str = "", goal: str = "", outcome: str = "success") -> dict:
        return self._store(COLLECTION_PROCEDURAL, text, importance, tags, trace_id, goal, outcome)

    def store(self, text: str, memory_type: str = "semantic", importance: int = 5, tags: str = "", trace_id: str = "", goal: str = "", outcome: str = "unknown", tools_used: str = "", source: str = "") -> dict:
        if memory_type not in ALL_COLLECTIONS:
            memory_type = COLLECTION_SEMANTIC
        return self._store(memory_type, text, importance, tags, trace_id, goal, outcome, tools_used, source)

    # ── Recall Delegators ─────────────────────────────────────────────────

    def recall(self, query: str, top_k: int = None, collections: list[str] = None, min_score: float = 0.5, tags_filter: str = "", trace_id: str = "") -> list[dict]:
        return read_ops.execute_recall(self, query, top_k, collections, min_score, tags_filter, trace_id)

    def recall_context(self, query: str, top_k: int = None, collections: list[str] = None, trace_id: str = "") -> str:
        return read_ops.execute_recall_context(self, query, top_k, collections, trace_id)

    # ── Maintenance (Temporary hold until Phase 4) ────────────────────────
    
    def delete(self, query: str, collections: list[str] = None, threshold: float = None, confirm_ids: list[str] = None) -> dict:
        from core.memory_backend.maintenance import execute_delete
        return execute_delete(self, query, collections, threshold, confirm_ids)

    def prune(self, max_age_days: int = 30, min_importance: int = 3, dry_run: bool = True, collections: list[str] = None) -> dict:
        from core.memory_backend.maintenance import execute_prune
        return execute_prune(self, max_age_days, min_importance, dry_run, collections)

    def summarize(self, collections: list[str] = None, top_n: int = 30, store_result: bool = True, trace_id: str = "") -> dict:
        from core.memory_backend.maintenance import execute_summarize
        return execute_summarize(self, collections, top_n, store_result, trace_id)

    def stats(self) -> dict:
        from core.memory_backend.maintenance import execute_stats
        return execute_stats(self)

    # ── Maintenance (To be extracted in Phase 4) ──────────────────────────
    # We will move delete, prune, summarize, and stats in the next phase.
    # For now, they remain as they were, or we can stub them if you prefer.
    # Actually, let's keep the original implementations here temporarily 
    # so your agent doesn't crash before Phase 4.