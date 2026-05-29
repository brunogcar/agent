"""
core/memory_backend/telemetry.py — Memory Recall Telemetry Buffer.
Records memory recalls in RAM and batches updates to ChromaDB periodically.
Prevents SQLite WAL contention and lock contention on the hot read path.
"""
from __future__ import annotations

import threading
import time
import logging

logger = logging.getLogger(__name__)

class RecallTracker:
    def __init__(self):
        self._lock = threading.Lock()
        # Key: (collection, memory_id) -> {"count": int, "last_at": float, "last_by": str}
        self._pending: dict[tuple[str, str], dict] = {}
        
    def record_recall(self, collection: str, memory_id: str, trace_id: str = "") -> None:
        """Record a recall in RAM (0ms latency)."""
        if not memory_id or not collection:
            return
        with self._lock:
            key = (collection, memory_id)
            if key not in self._pending:
                self._pending[key] = {
                    "count": 0, 
                    "last_at": time.time(), 
                    "last_by": trace_id
                }
            self._pending[key]["count"] += 1
            self._pending[key]["last_at"] = time.time()
            self._pending[key]["last_by"] = trace_id
            
    def flush(self, store) -> int:
        """
        Flush pending recall counts to ChromaDB metadata in a single batched write.
        Acquires the store's write lock to prevent collisions with memory writes.
        """
        with self._lock:
            if not self._pending:
                return 0
            pending_copy = self._pending.copy()
            self._pending.clear()
            
        updated = 0
        try:
            with store._write_lock:
                # Group by collection for efficient batch updates
                grouped: dict[str, dict[str, dict]] = {}
                for (col, mem_id), stats in pending_copy.items():
                    grouped.setdefault(col, {})[mem_id] = stats
                    
                for col_name, mem_stats in grouped.items():
                    try:
                        col = store._col(col_name)
                        ids = list(mem_stats.keys())
                        
                        # Fetch current metadata to increment counts
                        current = col.get(ids=ids, include=["metadatas"])
                        
                        if not current or not current["ids"]:
                            continue
                            
                        new_metadatas = []
                        for i, m_id in enumerate(current["ids"]):
                            meta = current["metadatas"][i] or {}
                            stats = mem_stats[m_id]
                            
                            meta["recall_count"] = meta.get("recall_count", 0) + stats["count"]
                            meta["last_recalled_at"] = stats["last_at"]
                            meta["last_recalled_by"] = stats["last_by"]
                            new_metadatas.append(meta)
                            
                        col.update(ids=current["ids"], metadatas=new_metadatas)
                        updated += len(current["ids"])
                    except Exception as e:
                        logger.warning(f"Telemetry flush failed for {col_name}: {e}")
                        # 🔴 Failure Recovery: Merge failed stats back into buffer for next cycle
                        with self._lock:
                            for m_id, stats in mem_stats.items():
                                key = (col_name, m_id)
                                if key not in self._pending:
                                    self._pending[key] = stats
                                else:
                                    self._pending[key]["count"] += stats["count"]
        except Exception as e:
            logger.warning(f"Telemetry flush lock failed: {e}")
            
        return updated

# Singleton
tracker = RecallTracker()