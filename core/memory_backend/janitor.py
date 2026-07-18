"""
core/memory_backend/janitor.py
Handles archival of old episodic memories to episodic_archive.
"""
from __future__ import annotations
import time
from core.config import cfg
from core.tracer import tracer

def archive_old_episodes() -> dict:
    """Moves episodic memories older than cfg.archive_age_days to episodic_archive."""
    # [v1.1 FIX] Create a unique trace_id for this archival run.
    # Previously used the literal string "janitor" as trace_id, causing
    # trace collisions. See: docs/core/observability/CHANGELOG.md (v1.1)
    _tid = tracer.new_trace("janitor", goal="archive old episodes")
    stats = {"archived": 0, "error": None}
    try:
        import chromadb  # LAZY IMPORT
        client = chromadb.PersistentClient(path=str(cfg.memory_chroma_path))
        epi_col = client.get_collection("episodic")
        arch_col = client.get_or_create_collection("episodic_archive")
        
        all_epi = epi_col.get(include=["documents", "metadatas"])
        if not all_epi["ids"]:
            return stats
            
        now = int(time.time())
        archive_age_secs = cfg.archive_age_days * 86400
        
        ids_to_archive = []
        docs_to_archive = []
        metas_to_archive = []
        
        for i, meta in enumerate(all_epi["metadatas"]):
            created_at = meta.get("timestamp", meta.get("created_at", 0))
            if isinstance(created_at, (int, float)) and (now - created_at > archive_age_secs):
                ids_to_archive.append(all_epi["ids"][i])
                docs_to_archive.append(all_epi["documents"][i])
                metas_to_archive.append(meta)
        
        if ids_to_archive:
            arch_col.add(ids=ids_to_archive, documents=docs_to_archive, metadatas=metas_to_archive)
            epi_col.delete(ids=ids_to_archive)
            stats["archived"] = len(ids_to_archive)
            
    except Exception as e:
        stats["error"] = str(e)
        tracer.error(_tid, "archive_episodes", str(e))
        
    return stats
