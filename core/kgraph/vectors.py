"""
core/kgraph/vectors.py
Helper to get or create project-specific ChromaDB collections + populate
codebase embeddings for semantic search.

[#3] ChromaDB vector indexing for the understand workflow.

[v1.4.1 P1-3] Project-scoped ChromaDB path. Was: hardcoded
`cfg.agent_root / ".understand" / "chroma"` — used the AGENT root's .understand
for ALL projects (workspace + agent_root alike). This created an asymmetry:
deleting a project's `.understand/` directory deleted the kg.db but left
the project's vectors orphaned in the agent_root's `.understand/chroma/`.

Now: `get_project_vector_collection(pm: ProjectManager)` computes the path
from `pm`:
  - Agent root:   cfg.memory_root / "understand" / "chroma"
                  (per the user's request — vectors for the agent root
                  itself live under memory_db/understand/chroma/, keeping
                  them with the rest of the memory store)
  - Projects:     pm.artifact_root / "chroma"
                  (i.e. {project}/.understand/chroma/ — same as before for
                  the agent_root case under the old layout, but now project
                  vectors are properly per-project)

Migration: existing agent_root ChromaDB data at `agent_root/.understand/chroma/`
is orphaned by this change. Operators should delete that directory and re-run
understand. We do NOT auto-migrate (would be a surprise move of multi-GB
vector stores).
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

def get_project_vector_collection(pm: Any) -> Any:
    """
    Lazy import and get/create a ChromaDB collection for a specific project.

    [v1.4.1 P1-3] Signature changed: was `project_id: str`, now `pm: ProjectManager`.
    The path is computed from `pm` so it's properly project-scoped:
      - Agent root → cfg.memory_root / "understand" / "chroma"
      - Workspace project → pm.artifact_root / "chroma"  (i.e. {project}/.understand/chroma/)

    Keeps project vectors isolated from the main memory_db.
    Reuses the same PersistentClient instance per path (singleton pattern).

    [#3] The collection stores per-definition code embeddings (functions,
    classes, module docstrings) for semantic search. Embeddings are generated
    by core.kgraph.embeddings.embed_texts() and passed explicitly to add() —
    no ChromaDB default embedding function needed.

    v1.3.1: Uses a project-specific ChromaDB path inside .understand/chroma
    instead of the shared cfg.memory_chroma_path. The shared path caused
    "An instance of Chroma already exists with different settings" errors
    because the main memory store creates collections WITHOUT hnsw:space
    metadata, while the kgraph creates collections WITH hnsw:space=cosine.
    ChromaDB requires all collections on a PersistentClient to use the same
    settings — so sharing the path between memory + kgraph is broken.
    The .understand/chroma path keeps them isolated (as the comment always
    said it should).

    Args:
        pm: A `ProjectManager` instance. The function reads `pm.is_agent_root`,
            `pm.artifact_root`, and `pm.project_id` from it. Accepting `pm`
            instead of `project_id` lets us compute the right per-project path
            without re-instantiating ProjectManager (which would re-walk the
            source tree for stats).
    """
    import chromadb

    # [v1.4.1 P1-3] Compute the chroma path from the ProjectManager.
    if getattr(pm, "is_agent_root", False):
        # Agent root: vectors under memory_db/understand/chroma/ (per user
        # request — keeps them with the rest of the memory store).
        path = str(cfg.memory_root / "understand" / "chroma")
    else:
        # Workspace project: vectors under {project}/.understand/chroma/.
        path = str(Path(pm.artifact_root) / "chroma")

    # Reuse existing client for this path, or create and cache
    if path not in _chroma_clients:
        Path(path).mkdir(parents=True, exist_ok=True)
        _chroma_clients[path] = chromadb.PersistentClient(path=path)

    client = _chroma_clients[path]
    collection_name = f"kg_{pm.project_id}_embeddings"

    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

def query_similar_code(
    pm: Any,
    query: str,
    n_results: int = 10,
    trace_id: str = "",
) -> list[dict]:
    """[#3] Semantic search: find code definitions similar to a query string.

    [v1.4.1 P1-3] Signature changed: was `project_id: str`, now `pm: ProjectManager`.

    Returns a list of dicts: {file_path, name, type, line_start, line_end, distance, source}

    Returns empty list if embedding fails (graceful degradation).
    """
    from core.kgraph.embeddings import embed_texts

    # [v1.7] Per-project embedding model. Was: cfg.embedding_model (global).
    # Now: pm.get_embedding_model() reads .understand/config.json override.
    model = pm.get_embedding_model() if hasattr(pm, "get_embedding_model") else ""
    query_embedding = embed_texts([query], trace_id=trace_id, model=model)
    if query_embedding is None:
        return []

    collection = get_project_vector_collection(pm)

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
