"""
core/memory_backend/client.py — ChromaDB client initialization.
Includes DeepSeek timeout fix and FastAPI reload guard.
"""
from __future__ import annotations

import sys
import threading
import concurrent.futures

from core.config import cfg

# Thread lock specifically for lazy-loading the ChromaDB client
_client_lock = threading.Lock()
_client_instance = None

def get_client(timeout: int = 60):
    """
    Create or return the cached ChromaDB client with a hard timeout.
    
    HIG-05 + DeepSeek fix: PersistentClient can hang indefinitely on slow/flaky storage.
    Wrap with concurrent.futures.timeout and graceful fallback.
    
    FastAPI Reload Guard: Uses double-checked locking to prevent duplicate 
    client instantiation during dev server reloads.
    """
    global _client_instance
    
    # FastAPI Reload Guard: Return immediately if already initialized
    if _client_instance is not None:
        return _client_instance

    with _client_lock:
        # Double-checked locking
        if _client_instance is not None:
            return _client_instance

        import chromadb
        from chromadb.config import Settings

        def _create():
            return chromadb.PersistentClient(
                path=str(cfg.memory_chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_create)
                client = future.result(timeout=timeout)
            print(f"[memory] ChromaDB client created successfully", file=sys.stderr)
            _client_instance = client
            return _client_instance

        except concurrent.futures.TimeoutError:
            print(f"[memory] ChromaDB creation timed out after {timeout}s", file=sys.stderr)
        except Exception as e:
            print(f"[memory] ChromaDB creation failed: {e}", file=sys.stderr)

        # Degraded fallback
        try:
            cfg.memory_chroma_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=str(cfg.memory_chroma_path),
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
            print("[memory] ChromaDB reconnected (degraded mode)", file=sys.stderr)
            _client_instance = client
            return _client_instance
        except Exception as e2:
            print(f"[memory] FATAL: Could not create ChromaDB client: {e2}", file=sys.stderr)
            raise