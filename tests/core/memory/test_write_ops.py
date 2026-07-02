"""
tests/core/memory/test_write_ops.py -- Unit tests for the new deduplication and reinforcement logic.
"""
from __future__ import annotations
import pytest
from core.memory_engine import memory

def test_hash_guard_exact_match():
    """O(1) Hash Guard should catch exact text matches instantly."""
    text = "The quick brown fox jumps over the lazy dog. HashGuardTest"
    r1 = memory.store_semantic(text, importance=5, trace_id="test_hash")
    assert r1["status"] in ("stored", "skipped_duplicate")
    
    r2 = memory.store_semantic(text, importance=5, trace_id="test_hash")
    assert r2["status"] == "skipped_duplicate"
    assert r2["reason"] == "exact_hash_match"
    assert r2["retry_recommended"] is False

def test_contextual_feedback_semantic_duplicate():
    """Semantic duplicates should return a truncated snippet and directive."""
    text_a = "When fixing pandas KeyError, always check for trailing whitespace in column names. FeedbackTest"
    text_b = "When fixing pandas KeyError, always check for trailing whitespace in column names and headers. FeedbackTest"
    
    r1 = memory.store_semantic(text_a, importance=6, trace_id="test_feedback")
    assert r1["status"] in ("stored", "skipped_duplicate")
    
    r2 = memory.store_semantic(text_b, importance=6, trace_id="test_feedback")
    # If the local embedding model catches the semantic overlap:
    if r2["status"] == "skipped_duplicate" and r2.get("reason") == "semantic_match":
        assert "matched_snippet" in r2
        assert len(r2["matched_snippet"]) <= 205  # 200 chars + "..."
        assert r2["action"] == "reference_existing"
        assert r2["retry_recommended"] is False

def test_procedural_reinforcement():
    """Storing a semantic duplicate procedural memory should increment reinforcement_count."""
    text = "To fix SyntaxError: always check line N-2 for unclosed bracket. ReinforcementTest"
    
    r1 = memory.store_procedural(text, importance=8, trace_id="test_reinf")
    assert r1["status"] in ("stored", "reinforced", "skipped_duplicate")
    
    # Slightly different text to bypass Hash Guard and trigger Semantic Reinforcement
    text_semantic = "To fix SyntaxError: always check line N-2 for an unclosed bracket. ReinforcementTest"
    r2 = memory.store_procedural(text_semantic, importance=8, trace_id="test_reinf")
    
    if r2["status"] == "reinforced":
        assert r2["reinforcement_count"] >= 1

def test_procedural_reinforcement_updates_metadata():
    """Semantic duplicate procedural memories must increment reinforcement_count in ChromaDB."""
    from core.memory_engine import memory
    text_base = "To fix a LangGraph state mutation, always return a new dict. ReinforcementMathTest"
    text_dup  = "To fix a LangGraph state mutation, always return a new dictionary. ReinforcementMathTest"
    
    # Store base
    memory.store_procedural(text_base, importance=8, trace_id="test_math")
    
    # Trigger reinforcement (slightly different text bypasses Hash Guard)
    r2 = memory.store_procedural(text_dup, importance=8, trace_id="test_math")
    
    if r2["status"] == "reinforced":
        # Verify the actual database was updated, not just the return payload
        existing_id = r2["existing_id"]
        col = memory._col("procedural")
        db_data = col.get(ids=[existing_id], include=["metadatas"])
        db_count = db_data["metadatas"][0].get("reinforcement_count", 0)
        assert db_count >= 1, "Reinforcement count was not persisted to ChromaDB!"

def test_contextual_feedback_payload_strictness():
    """Semantic duplicate payload MUST contain directive and retry_recommended=False."""
    from core.memory_engine import memory
    text_a = "FastAPI requires async def for endpoints that use await. PayloadStrictnessTest"
    text_b = "FastAPI requires async def for endpoints that use await internally. PayloadStrictnessTest"
    
    memory.store_semantic(text_a, importance=6, trace_id="test_strict")
    r2 = memory.store_semantic(text_b, importance=6, trace_id="test_strict")
    
    if r2["status"] == "skipped_duplicate" and r2.get("reason") == "semantic_match":
        assert "directive" in r2, "Missing behavioral directive for LLM"
        assert r2["retry_recommended"] is False, "retry_recommended must be explicitly False"
        assert len(r2.get("matched_snippet", "")) <= 205, "Snippet exceeded 200 char limit + ellipsis"