"""
core/kgraph/vectors.py
Helper to get or create project-specific ChromaDB collections.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

# [P1 FIX] Module-level cache for ChromaDB clients keyed by path.
# Prevents creating a new PersistentClient on every call, which is
# expensive (opens SQLite + loads embedding model metadata).
_chroma_clients: dict[str, Any] = {}

def get_project_vector_collection(project_id: str) -> Any:
    """
    Lazy import and get/create a ChromaDB collection for a specific project.
    Keeps project vectors isolated from the main memory_db.
    Reuses the same PersistentClient instance per path (singleton pattern).
    """
    import chromadb
    from core.config import cfg

    path = str(cfg.memory_chroma_path)

    # Reuse existing client for this path, or create and cache
    if path not in _chroma_clients:
        _chroma_clients[path] = chromadb.PersistentClient(path=path)

    client = _chroma_clients[path]
    collection_name = f"kg_{project_id}_embeddings"

    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
