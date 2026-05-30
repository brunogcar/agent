"""
core/memory_backend/eviction.py — Async WAL-spill for evicted context.
Ensures evicted working memory is persisted to disk immediately (crash-safe)
and flushed to ChromaDB asynchronously (non-blocking).
"""
from __future__ import annotations

import json
import time
import os
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
        self._lock = threading.RLock()

    def push(self, text: str, metadata: dict):
        """Push an eviction payload. 1. Append to JSONL (Crash-safe + fsync) 2. Add to RAM queue."""
        payload = {"text": text, "metadata": metadata, "ts": time.time()}
        try:
            with self._lock:
                with open(QUEUE_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"[Eviction] Disk spill failed: {e}")
        self._queue.put(payload)

    def replay_and_get_batch(self, max_size: int = 50) -> list[dict]:
        """Read from disk & RAM, return batch, ATOMICALLY rewrite disk with remaining."""
        disk_items = []
        tmp_file = QUEUE_FILE.with_suffix(".jsonl.tmp")
        
        with self._lock:
            if QUEUE_FILE.exists():
                try:
                    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try: disk_items.append(json.loads(line))
                                except json.JSONDecodeError: pass
                except Exception as e:
                    logger.error(f"[Eviction] Failed to read disk queue: {e}")
                    
            while True:
                try: disk_items.append(self._queue.get_nowait())
                except Empty: break
                    
            batch = disk_items[:max_size]
            remaining = disk_items[max_size:]
            
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    for item in remaining: f.write(json.dumps(item) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_file, QUEUE_FILE)
            except Exception as e:
                logger.error(f"[Eviction] Failed to rewrite disk queue: {e}")
                if tmp_file.exists():
                    try: tmp_file.unlink()
                    except Exception: pass
        return batch

eviction_queue = EvictionQueue()

def flusher_loop():
    from core.memory import memory
    logger.info("[Eviction] Flusher thread started.")
    while True:
        time.sleep(5)
        batch = eviction_queue.replay_and_get_batch()
        if not batch: continue
        try:
            for item in batch:
                memory.store(text=item["text"], collection="episodic", tags="evicted,working-memory", **item["metadata"])
        except Exception as e:
            logger.error(f"[Eviction] Flush failed: {e}")