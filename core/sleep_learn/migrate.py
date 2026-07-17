"""core/sleep_learn/migrate.py — Migration script: procedural_meta → procedural (Commit 4b).

Run this ONCE to migrate rules from the isolated `procedural_meta` collection
to the unified `procedural` collection. After migration, `procedural_meta` can
be safely dropped.

Usage:
    python -c "from core.sleep_learn.migrate import migrate_rules; print(migrate_rules())"

Or via the memory tool (after adding a 'migrate' action — not included here).

Migration steps (minimax's 3-sub-step approach):
1. Read all rules from procedural_meta
2. For each, check if a matching rule exists in procedural (by text_hash)
3. If not, write to procedural with the unified schema
4. If yes, merge (keep the higher confidence, union the source_trace_ids)
5. Verify: count(procedural) >= max(count(original procedural), count(procedural_meta))
6. Drop procedural_meta

The script is idempotent — running it twice is safe (the second run finds
nothing to migrate because procedural_meta is empty).
"""
from __future__ import annotations

import json
import time
from typing import Any

from core.tracer import tracer


def migrate_rules(dry_run: bool = False) -> dict:
    """Migrate rules from procedural_meta to procedural.
    
    Args:
        dry_run: If True, report what would be migrated without writing.
    
    Returns:
        {"migrated": int, "merged": int, "skipped": int, "errors": int, "dry_run": bool}
    """
    from core.sleep_learn.config import _SLEEP_LEARN_DB_PATH, SLEEP_LEARN_COLLECTION_NAME
    from core.memory_backend.rule_schema import build_unified_metadata, compute_text_hash
    from core.memory_engine import memory
    
    stats = {"migrated": 0, "merged": 0, "skipped": 0, "errors": 0, "dry_run": dry_run}
    
    # 1. Open the old procedural_meta collection
    try:
        import chromadb
        old_client = chromadb.PersistentClient(path=str(_SLEEP_LEARN_DB_PATH))
        old_col = old_client.get_collection(name=SLEEP_LEARN_COLLECTION_NAME)
    except Exception as e:
        # Collection doesn't exist — nothing to migrate
        stats["note"] = f"procedural_meta not found: {e}"
        return stats
    
    # 2. Read all rules from procedural_meta
    try:
        all_data = old_col.get(include=["documents", "metadatas"])
    except Exception as e:
        stats["errors"] = 1
        stats["note"] = f"Failed to read procedural_meta: {e}"
        return stats
    
    ids = all_data.get("ids", [])
    docs = all_data.get("documents", [])
    metas = all_data.get("metadatas", [])
    
    if not ids:
        stats["note"] = "procedural_meta is empty — nothing to migrate"
        return stats
    
    # 3. Get the unified procedural collection
    proc_col = memory._col("procedural")
    
    # 4. Build a hash index of existing procedural rules (for dedup)
    try:
        existing_data = proc_col.get(include=["metadatas"])
        existing_hashes = {}
        for i, meta in enumerate(existing_data.get("metadatas", [])):
            h = meta.get("text_hash", "")
            if h:
                existing_hashes[h] = existing_data["ids"][i]
    except Exception:
        existing_hashes = {}
    
    # 5. Migrate each rule
    for rule_id, doc, meta in zip(ids, docs, metas):
        try:
            text = doc or ""
            if not text.strip():
                stats["skipped"] += 1
                continue
            
            # Build unified metadata from the old sleep_learn shape
            confidence = float(meta.get("confidence_score", meta.get("confidence", 0.8)))
            source_memory_id = meta.get("source_memory_id", "")
            created_at = meta.get("created_at", int(time.time()))
            last_accessed = meta.get("last_accessed_at", created_at)
            recall_count = meta.get("recall_count", 0)
            
            # Check for existing rule by text_hash (dedup)
            text_hash = compute_text_hash(text)
            if text_hash in existing_hashes:
                # Merge: update the existing rule's confidence + source_trace_ids
                existing_id = existing_hashes[text_hash]
                if not dry_run:
                    existing_meta = proc_col.get(ids=[existing_id], include=["metadatas"])
                    if existing_meta.get("metadatas"):
                        em = existing_meta["metadatas"][0]
                        # Keep the higher confidence
                        em["confidence"] = max(float(em.get("confidence", 0)), confidence)
                        # Union source_trace_ids
                        old_ids = em.get("source_trace_ids", "")
                        if source_memory_id and source_memory_id not in old_ids:
                            em["source_trace_ids"] = (old_ids + "," + source_memory_id)[:500]
                        em["provenance_count"] = len([t for t in em["source_trace_ids"].split(",") if t.strip()])
                        proc_col.update(ids=[existing_id], metadatas=[em])
                stats["merged"] += 1
                continue
            
            # Build the unified metadata
            unified = build_unified_metadata(
                text=text,
                source="sleep_learn",
                confidence=confidence,
                source_memory_id=source_memory_id,
                source_trace_ids=source_memory_id,
                created_at=created_at,
                last_accessed_at=last_accessed,
                recall_count=recall_count,
            )
            
            if not dry_run:
                proc_col.add(
                    ids=[rule_id],  # keep the same ID for traceability
                    documents=[text],
                    metadatas=[unified],
                )
                existing_hashes[text_hash] = rule_id
            
            stats["migrated"] += 1
            
        except Exception as e:
            tracer.error("migration", "migrate_rules", f"Failed to migrate rule {rule_id}: {e}")
            stats["errors"] += 1
    
    # 6. Verify (only if not dry_run)
    if not dry_run and stats["migrated"] > 0:
        try:
            new_count = proc_col.count()
            old_count = len(ids)
            stats["verified"] = new_count >= old_count
            stats["procedural_count"] = new_count
        except Exception:
            pass
    
    # 7. Drop procedural_meta (only if not dry_run + migration succeeded)
    if not dry_run and stats["errors"] == 0:
        try:
            old_client.delete_collection(name=SLEEP_LEARN_COLLECTION_NAME)
            stats["dropped"] = True
            tracer.step("migration", "migrate_rules", f"Dropped {SLEEP_LEARN_COLLECTION_NAME}")
        except Exception as e:
            stats["dropped"] = False
            stats["drop_error"] = str(e)
    
    tracer.step("migration", "migrate_rules", f"Migration complete: {stats}")
    return stats
