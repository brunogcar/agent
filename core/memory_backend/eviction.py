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
        """
        Push an eviction payload.
        1. Append to JSONL (Crash-safe + fsync)
        2. Add to RAM queue (For background flusher)
        """
        payload = {
            "text": text,
            "metadata": metadata,
            "ts": time.time()
        }

        # 1. Disk Spill (Thread-Safe Append + fsync)
        try:
            with self._lock:
                with open(QUEUE_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"[Eviction] Disk spill failed: {e}")

        # 2. RAM Queue
        self._queue.put(payload)

    def get_all_pending(self) -> list[dict]:
        """
        Read all pending items from disk and RAM without modifying state.
        Used by the flusher to inspect what needs to be processed.
        """
        items = []
        with self._lock:
            if QUEUE_FILE.exists():
                try:
                    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    parsed = json.loads(line)
                                    if isinstance(parsed, dict) and "text" in parsed and "metadata" in parsed and isinstance(parsed.get("metadata"), dict):
                                        items.append(parsed)
                                    else:
                                        logger.warning(f"[Eviction] Skipping malformed queue entry: {str(line)[:100]}")
                                except json.JSONDecodeError:
                                    pass
                except Exception as e:
                    logger.error(f"[Eviction] Failed to read disk queue: {e}")

            while True:
                try:
                    items.append(self._queue.get_nowait())
                except Empty:
                    break

        return items

    def commit_success(self, remaining_items: list[dict]):
        """
        Call ONLY after successful ChromaDB flush.
        Rewrites disk with remaining items using atomic os.replace.
        """
        tmp_file = QUEUE_FILE.with_suffix(".jsonl.tmp")
        with self._lock:
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    for item in remaining_items:
                        f.write(json.dumps(item) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                    os.replace(tmp_file, QUEUE_FILE)
            except Exception as e:
                logger.error(f"[Eviction] Failed to rewrite disk queue: {e}")
                if tmp_file.exists():
                    try:
                        tmp_file.unlink()
                    except Exception:
                        pass

# Singleton
eviction_queue = EvictionQueue()

def flusher_loop():
    """Background thread that flushes the queue to ChromaDB."""
    from core.memory_engine import memory

    logger.info("[Eviction] Flusher thread started.")
    while True:
        time.sleep(5)

        # Phase 1: Read (Does NOT modify disk)
        all_pending = eviction_queue.get_all_pending()
        if not all_pending:
            continue

        batch = all_pending[:50]
        remaining = all_pending[50:]

        logger.info(f"[Eviction] Flushing {len(batch)} items to ChromaDB...")
        try:
            # Phase 2: Flush
            for item in batch:
                if not isinstance(item, dict):
                    logger.warning(f"[Eviction] Skipping non-dict item: {type(item)}")
                    continue
                if "text" not in item or "metadata" not in item:
                    logger.warning(f"[Eviction] Skipping malformed item: {list(item.keys()) if isinstance(item, dict) else item}")
                    continue
                if not isinstance(item["metadata"], dict):
                    logger.warning(f"[Eviction] Skipping item with non-dict metadata: {type(item['metadata'])}")
                    continue

                # Safe kwargs: unpack metadata first, then override with our values
                kwargs = dict(item["metadata"])
                kwargs["text"] = item["text"]
                kwargs["memory_type"] = "episodic"
                kwargs["tags"] = "evicted,working-memory"
                memory.store(**kwargs)

            # Phase 3: Commit (ONLY truncates disk AFTER successful ChromaDB write)
            eviction_queue.commit_success(remaining)
        except Exception as e:
            logger.error(f"[Eviction] Flush failed: {e}")
            # FAILURE: Do NOT touch the disk file. Items remain on disk for next restart.
