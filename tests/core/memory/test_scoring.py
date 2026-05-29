"""
tests/core/memory/test_scoring.py -- Unit tests for memory scoring and query rewriting.
"""
from __future__ import annotations
import time
import pytest
from core.memory_backend.scoring import _decay_score, _rewrite_query
from core.config import cfg

# -- Decay scoring ------------------------------------------------------------

def test_decay_score_at_zero_age():
    assert _decay_score(8, int(time.time()), "episodic") == pytest.approx(8.0, abs=0.05)

def test_decay_score_at_30_days():
    ts = int(time.time()) - cfg.memory_decay_days * 86400
    assert _decay_score(10, ts, "episodic") == pytest.approx(10 * 0.3, abs=0.1)

def test_decay_score_floor():
    ancient = int(time.time()) - 365 * 86400
    assert _decay_score(5, ancient, "episodic") >= 5 * 0.3 - 0.01

def test_procedural_decay_bypass():
    """Procedural memories should bypass time decay."""
    ancient = int(time.time()) - 365 * 86400
    score = _decay_score(8, ancient, "procedural", reinforcement_count=0)
    assert score == pytest.approx(8.0, abs=0.05)

def test_procedural_reinforcement_boost():
    """Reinforcement should apply a capped logarithmic boost."""
    now = int(time.time())
    base_score = _decay_score(8, now, "procedural", reinforcement_count=0)
    boosted_score = _decay_score(8, now, "procedural", reinforcement_count=5)
    assert boosted_score > base_score
    
    # Cap check: count=10 and count=20 should yield similar scores due to min(count, 10) cap
    score_10 = _decay_score(8, now, "procedural", reinforcement_count=10)
    score_20 = _decay_score(8, now, "procedural", reinforcement_count=20)
    assert score_10 == pytest.approx(score_20, abs=0.01)

# -- Query rewriter -----------------------------------------------------------

def test_rewriter_preserves_question_starters():
    assert _rewrite_query("how do i fix syntax errors") == "how do i fix syntax errors"
    assert _rewrite_query("what is chromadb") == "what is chromadb"

def test_rewriter_strips_pure_fillers():
    result = _rewrite_query("please tell me about database")
    assert "please" not in result
    assert "database" in result

def test_rewriter_expands_abbreviations():
    assert "python" in _rewrite_query("fix py error")
    assert "error" in _rewrite_query("fix err cfg")

def test_rewriter_handles_empty_input():
    assert _rewrite_query("") == "general"