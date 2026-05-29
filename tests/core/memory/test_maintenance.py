"""
tests/core/memory/test_maintenance.py -- Unit tests for memory maintenance.
"""
from __future__ import annotations
from core.memory import memory

def test_stats_structure():
    stats = memory.stats()
    for col in ["episodic", "semantic", "procedural"]:
        assert col in stats
        assert isinstance(stats[col].get("count"), int)
        assert stats[col]["count"] >= 0

def test_prune_dry_run_no_delete():
    before = memory.stats()
    memory.prune(dry_run=True, max_age_days=0, min_importance=10)
    after  = memory.stats()
    for col in ["episodic", "semantic", "procedural"]:
        assert before[col]["count"] == after[col]["count"]

def test_prune_protects_procedural_by_default():
    before = memory.stats()["procedural"]["count"]
    memory.prune(dry_run=False, max_age_days=0, min_importance=10)
    assert memory.stats()["procedural"]["count"] == before

def test_hash_cache_syncs_on_delete():
    """Deleting a memory MUST remove its hash from the O(1) in-memory guard."""
    from core.memory import memory
    text = "Ghost Hash Test: This text will be deleted and re-stored."
    
    # 1. Store it
    r1 = memory.store_semantic(text, importance=5, trace_id="test_ghost")
    assert r1["status"] in ("stored", "skipped_duplicate")
    
    # 2. Delete it
    del_res = memory.delete(query=text, confirm_ids=[r1.get("id")])
    assert del_res["status"] == "deleted" or del_res["count"] >= 1
    
    # 3. Try to store it again. If the hash cache wasn't cleared, this will fail with "exact_hash_match"
    r2 = memory.store_semantic(text, importance=5, trace_id="test_ghost")
    assert r2["status"] == "stored", f"Hash cache was not cleared on delete! Got: {r2}"