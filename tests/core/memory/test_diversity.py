"""tests/core/memory/test_diversity.py — Phase 6 diversity enforcement tests."""
from __future__ import annotations
from core.memory import memory
from core.memory_backend.maintenance import execute_diversity_maintenance

def test_diversity_dry_run_returns_metrics():
    """Dry run should calculate clusters without mutating DB."""
    # Seed 2 near-identical procedural memories
    memory.store_procedural("Rule A: Always check config before writing.", importance=8, trace_id="div_test")
    memory.store_procedural("Rule A: Always verify config before writing files.", importance=8, trace_id="div_test")
    
    result = execute_diversity_maintenance(memory, dry_run=True)
    assert result["status"] == "success"
    assert result["metrics"]["dry_run"] is True
    # Cleanup
    memory.prune(dry_run=False, max_age_days=0, min_importance=1, collections=["procedural"])

def test_diversity_contradiction_guard():
    """Opposing rules must be flagged, not merged."""
    from unittest.mock import patch
    
    text1 = "Rule X: Never use eval() in production code."
    text2 = "Rule X: Always use eval() in production code."
    
    r1 = memory.store_procedural(text1, importance=9, outcome="success", trace_id="contradict")
    r2 = memory.store_procedural(text2, importance=9, outcome="failure", trace_id="contradict")
    
    id1 = r1.get("id") or r1.get("existing_id")
    id2 = r2.get("id") or r2.get("existing_id")
    
    col = memory._col("procedural")
    
    # 🔴 DETERMINISTIC FIX: Mock the vector query to FORCE clustering.
    # Bypasses embedding model variance so we strictly test the contradiction guard logic.
    def mock_query(query_texts, n_results, include):
        return {
            "ids": [[id1, id2]],
            "distances": [[0.01, 0.02]],
            "metadatas": [[{"outcome": "success"}, {"outcome": "failure"}]],
            "documents": [[text1, text2]]
        }
        
    with patch.object(col, 'query', side_effect=mock_query):
        result = execute_diversity_maintenance(memory, dry_run=False)
        
    assert result["metrics"]["contradictions_detected"] >= 1, "Contradiction guard failed to detect polarity mismatch"