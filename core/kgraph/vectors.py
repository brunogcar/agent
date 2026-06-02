"""
core/kgraph/vectors.py
Helper to get or create project-specific ChromaDB collections.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

def get_project_vector_collection(project_id: str) -> Any:
    """
    Lazy import and get/create a ChromaDB collection for a specific project.
    Keeps project vectors isolated from the main memory_db.
    """
    import chromadb
    from core.config import cfg
    
    # We use the main memory path but a uniquely named collection
    client = chromadb.PersistentClient(path=str(cfg.memory_chroma_path))
    collection_name = f"kg_{project_id}_embeddings"
    
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
