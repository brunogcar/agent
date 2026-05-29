"""
core/eviction_queue.py — Async WAL-spill for evicted context.
Ensures evicted working memory is persisted to disk immediately (crash-safe)
and flushed to ChromaDB asynchronously (non-blocking).
"""
from __future__ import annotations

import json
import time
import threading
import logging
from pathlib import Path
from queue import Queue, Empty

from core.config import cfg

logger = logging.getLogger(__name__)

QUEUE_FILE = cfg.workspace_root / ".eviction_queue.jsonl"

class EvictionQueue:
    def __init__(self):
        self._queue = Queue()
        self._lock = threading.Lock()
        
    def push(self, text: str, metadata: dict):
        """
        Push an eviction payload.
        1. Append to JSONL (Crash-safe)
        2. Add to RAM queue (For background flusher)
        """
        payload = {
            "text": text,
            "metadata": metadata,
            "ts": time.time()
        }
        
        # 1. Disk Spill (Atomic Append)
        try:
            with open(QUEUE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.error(f"[Eviction] Disk spill failed: {e}")
            
        # 2. RAM Queue
        self._queue.put(payload)
        
    def get_batch(self, max_size: int = 50) -> list[dict]:
        """Get a batch of items for flushing."""
        batch = []
        try:
            while len(batch) < max_size:
                batch.append(self._queue.get_nowait())
        except Empty:
            pass
        return batch
        
    def clear_disk_queue(self):
        """Delete the JSONL file after successful flush."""
        try:
            if QUEUE_FILE.exists():
                QUEUE_FILE.unlink()
        except Exception:
            pass

# Singleton
eviction_queue = EvictionQueue()

def flusher_loop():
    """Background thread that flushes the queue to ChromaDB."""
    from core.memory import memory
    
    logger.info("[Eviction] Flusher thread started.")
    while True:
        time.sleep(5) # Flush every 5 seconds
        batch = eviction_queue.get_batch()
        if not batch:
            continue
            
        logger.info(f"[Eviction] Flushing {len(batch)} items to ChromaDB...")
        try:
            for item in batch:
                memory.store(
                    text=item["text"],
                    collection="episodic",
                    tags="evicted,working-memory",
                    **item["metadata"]
                )
            # Success: Clear disk queue
            eviction_queue.clear_disk_queue()
        except Exception as e:
            logger.error(f"[Eviction] Flush failed: {e}")
            # Items remain in JSONL for next restart recovery