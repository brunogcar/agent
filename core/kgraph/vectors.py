"""
core/kgraph/vectors.py
Helper to get or create project-specific ChromaDB collections + populate
codebase embeddings for semantic search.

[#3] ChromaDB vector indexing for the understand workflow.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

from core.config import cfg
from core.tracer import tracer

# [P1 FIX] Module-level cache for ChromaDB clients keyed by path.
# Prevents creating a new PersistentClient on every call, which is
# expensive (opens SQLite + loads embedding model metadata).
_chroma_clients: dict[str, Any] = {}

def get_project_vector_collection(project_id: str) -> Any:
    """
    Lazy import and get/create a ChromaDB collection for a specific project.
    Keeps project vectors isolated from the main memory_db.
    Reuses the same PersistentClient instance per path (singleton pattern).

    [#3] The collection stores per-definition code embeddings (functions,
    classes, module docstrings) for semantic search. Embeddings are generated
    by core.kgraph.embeddings.embed_texts() and passed explicitly to add() —
    no ChromaDB default embedding function needed.
    """
    import chromadb

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


def upsert_file_vectors(
    project_id: str,
    file_path: str,
    definitions: list[dict],
    trace_id: str = "",
) -> int:
    """[#3] Upsert code embeddings for a file's top-level definitions.

    1. Deletes old vectors for this file (definitions may have been removed/renamed)
    2. Embeds the source code of each definition via LM Studio
    3. Stores in ChromaDB with metadata (file_path, name, type, line range)

    Returns the number of vectors stored. Returns 0 if embedding fails
    (graceful degradation — the graph edges in SQLite are unaffected).

    Args:
        project_id: The project ID from ProjectManager.
        file_path: Relative file path (e.g. "core/config.py").
        definitions: List of dicts from extract_definitions(): {name, type, source, line_start, line_end}
        trace_id: For trace logging.
    """
    from core.kgraph.embeddings import embed_texts

    collection = get_project_vector_collection(project_id)

    # Delete old vectors for this file (handles renames/deletions)
    try:
        collection.delete(where={"file_path": file_path})
    except Exception:
        pass  # Collection may be empty on first run

    if not definitions:
        return 0

    # Embed all definitions in one batch
    texts = [d["source"] for d in definitions]
    embeddings = embed_texts(texts, trace_id=trace_id)

    if embeddings is None:
        # LM Studio not available — graceful degradation
        tracer.warning(
            trace_id, "vectors",
            f"Skipping vector indexing for {file_path} (embedding service unavailable)"
        )
        return 0

    if len(embeddings) != len(definitions):
        tracer.warning(
            trace_id, "vectors",
            f"Embedding count mismatch for {file_path}: "
            f"{len(embeddings)} embeddings for {len(definitions)} definitions"
        )
        return 0

    # Build IDs, metadata
    ids = [f"{project_id}:{file_path}:{d['name']}" for d in definitions]
    metadatas = [{
        "project_id": project_id,
        "file_path": file_path,
        "name": d["name"],
        "type": d["type"],
        "line_start": d["line_start"],
        "line_end": d["line_end"],
    } for d in definitions]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    return len(definitions)


def query_similar_code(
    project_id: str,
    query: str,
    n_results: int = 10,
    trace_id: str = "",
) -> list[dict]:
    """[#3] Semantic search: find code definitions similar to a query string.

    Returns a list of dicts: {file_path, name, type, line_start, line_end, distance, source}

    Returns empty list if embedding fails (graceful degradation).
    """
    from core.kgraph.embeddings import embed_texts

    query_embedding = embed_texts([query], trace_id=trace_id)
    if query_embedding is None:
        return []

    collection = get_project_vector_collection(project_id)

    try:
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            include=["metadatas", "documents", "distances"],
        )
    except Exception as e:
        tracer.warning(trace_id, "vectors", f"Vector query failed: {e}")
        return []

    if not results["metadatas"] or not results["metadatas"][0]:
        return []

    out = []
    for meta, doc, dist in zip(
        results["metadatas"][0],
        results["documents"][0],
        results["distances"][0],
    ):
        out.append({
            "file_path": meta.get("file_path", ""),
            "name": meta.get("name", ""),
            "type": meta.get("type", ""),
            "line_start": meta.get("line_start", 0),
            "line_end": meta.get("line_end", 0),
            "distance": dist,
            "source": doc,
        })
    return out
