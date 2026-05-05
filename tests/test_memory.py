"""
tests/test_memory.py -- Unit tests for memory/store.py

Run from D:/mcp/agent/:
    pytest tests/test_memory.py -v

Tests:
  - Decay scoring formula
  - Query rewriter preserves semantic meaning
  - Store/recall round-trip
  - Dedup thresholds per collection
  - Prune protects procedural collection
"""

from __future__ import annotations

import time
import pytest
import sys
from pathlib import Path

# Ensure agent root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Decay scoring ─────────────────────────────────────────────────────────────

def test_decay_score_at_zero_age():
    """Fresh memory: score = importance exactly."""
    from memory.store import _decay_score
    score = _decay_score(8, int(time.time()))
    assert score == pytest.approx(8.0, abs=0.05)


def test_decay_score_at_30_days():
    """At decay_days age, score should be at floor (importance * 0.3)."""
    from memory.store import _decay_score
    from core.config import cfg
    old_ts = int(time.time()) - cfg.memory_decay_days * 86400
    score  = _decay_score(10, old_ts)
    assert score == pytest.approx(10 * 0.3, abs=0.1)


def test_decay_score_floor():
    """Very old memories never score below importance * 0.3."""
    from memory.store import _decay_score
    ancient = int(time.time()) - 365 * 86400  # 1 year ago
    score   = _decay_score(5, ancient)
    assert score >= 5 * 0.3 - 0.01


def test_decay_score_ordering():
    """Higher importance + more recent = higher score."""
    from memory.store import _decay_score
    now    = int(time.time())
    recent = now - 86400        # 1 day ago
    old    = now - 30 * 86400   # 30 days ago
    assert _decay_score(8, recent) > _decay_score(8, old)
    assert _decay_score(9, old)   > _decay_score(5, old)


# ── Query rewriter ────────────────────────────────────────────────────────────

def test_rewriter_preserves_question_starters():
    """'how do i', 'what is', 'can you' must NOT be stripped."""
    from memory.store import _rewrite_query
    cases = [
        ("how do i fix syntax errors",   "how do i fix syntax errors"),
        ("what is chromadb",             "what is chromadb"),
        ("can you find the config",      "can you find config"),
        ("what are the best practices",  "what are best practices"),
    ]
    for query, expected in cases:
        result = _rewrite_query(query)
        assert result == expected, (
            f"rewrite({query!r}) = {result!r}, expected {expected!r}"
        )


def test_rewriter_strips_pure_fillers():
    """Pure grammatical fillers should be removed."""
    from memory.store import _rewrite_query
    result = _rewrite_query("please tell me about the database")
    assert "please" not in result
    assert "database" in result


def test_rewriter_expands_abbreviations():
    """Common abbreviations should be expanded."""
    from memory.store import _rewrite_query
    assert "python" in _rewrite_query("fix the py error")
    assert "error"  in _rewrite_query("fix the err in cfg")


def test_rewriter_never_returns_empty():
    """Rewriter must never return empty string."""
    from memory.store import _rewrite_query
    result = _rewrite_query("the a an")
    assert len(result.strip()) > 0


def test_rewriter_handles_empty_input():
    """Empty query gets a safe fallback."""
    from memory.store import _rewrite_query
    result = _rewrite_query("")
    assert result == "general"


# ── Store / recall round-trip ─────────────────────────────────────────────────

def test_store_and_recall_episodic():
    """Store an episodic memory and recall it."""
    from memory.store import memory
    text = f"test_store_episodic_{int(time.time())}"
    r    = memory.store_episodic(text, importance=7, goal="test", outcome="success")
    assert r["status"] in ("stored", "skipped_duplicate")

    results = memory.recall(text, top_k=1, collections=["episodic"])
    assert len(results) >= 1
    assert any(text in r["text"] for r in results)


def test_store_and_recall_semantic():
    """Store a semantic memory and recall it by similarity."""
    from memory.store import memory
    text = f"ChromaDB_unit_test_marker_{int(time.time())}"
    r    = memory.store_semantic(text, importance=6, tags="test,unit")
    assert r["status"] in ("stored", "skipped_duplicate")

    results = memory.recall(text, top_k=3, collections=["semantic"])
    assert any(text in r["text"] for r in results)


def test_store_and_recall_procedural():
    """Store a procedural memory and confirm it ranks well."""
    from memory.store import memory
    text = f"unit_test_procedure_{int(time.time())}_how_to_use_memory"
    r    = memory.store_procedural(text, importance=8, tags="test,procedure")
    assert r["status"] in ("stored", "skipped_duplicate")

    results = memory.recall(text, top_k=3, collections=["procedural"])
    assert any(text in r["text"] for r in results)


def test_recall_returns_sorted_by_score():
    """Recall results must be sorted by score descending."""
    from memory.store import memory
    results = memory.recall("test memory", top_k=10)
    scores  = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_memory_stats_returns_counts():
    """stats() must return count for all three collections."""
    from memory.store import memory
    stats = memory.stats()
    assert "episodic"   in stats
    assert "semantic"   in stats
    assert "procedural" in stats
    for col_data in stats.values():
        assert "count" in col_data
        assert isinstance(col_data["count"], int)


# ── Prune protection ──────────────────────────────────────────────────────────

def test_prune_dry_run_never_deletes():
    """Dry-run prune must not delete anything."""
    from memory.store import memory
    before = memory.stats()
    memory.prune(dry_run=True, max_age_days=0, min_importance=10)
    after  = memory.stats()
    for col in ["episodic", "semantic", "procedural"]:
        assert before[col]["count"] == after[col]["count"]


def test_prune_never_touches_procedural_automatically():
    """Auto-prune (default collections) must not affect procedural."""
    from memory.store import memory
    before_proc = memory.stats()["procedural"]["count"]
    # Prune episodic and semantic only (default behaviour)
    memory.prune(dry_run=False, max_age_days=0, min_importance=10)
    after_proc  = memory.stats()["procedural"]["count"]
    assert before_proc == after_proc, (
        "Procedural collection was modified by auto-prune -- should be protected"
    )
