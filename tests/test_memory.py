"""
tests/test_memory.py -- Unit tests for core/memory.py
Run from D:/mcp/agent/: pytest tests/test_memory.py -v
"""
from __future__ import annotations
import time, pytest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# -- Decay scoring ------------------------------------------------------------

def test_decay_score_at_zero_age():
    from core.memory import _decay_score
    assert _decay_score(8, int(time.time())) == pytest.approx(8.0, abs=0.05)

def test_decay_score_at_30_days():
    from core.memory import _decay_score
    from core.config import cfg
    ts = int(time.time()) - cfg.memory_decay_days * 86400
    assert _decay_score(10, ts) == pytest.approx(10 * 0.3, abs=0.1)

def test_decay_score_floor():
    from core.memory import _decay_score
    ancient = int(time.time()) - 365 * 86400
    assert _decay_score(5, ancient) >= 5 * 0.3 - 0.01

def test_decay_score_ordering():
    from core.memory import _decay_score
    now = int(time.time())
    assert _decay_score(8, now - 86400)     > _decay_score(8, now - 30*86400)
    assert _decay_score(9, now - 30*86400)  > _decay_score(5, now - 30*86400)

# -- Query rewriter -----------------------------------------------------------

def test_rewriter_preserves_question_starters():
    from core.memory import _rewrite_query
    cases = [
        ("how do i fix syntax errors", "how do i fix syntax errors"),
        ("what is chromadb",           "what is chromadb"),
        ("can you find config",        "can you find config"),
        ("what are best practices",    "what are best practices"),
    ]
    for q, expected in cases:
        got = _rewrite_query(q)
        assert got == expected, f"rewrite({q!r}) = {got!r}, expected {expected!r}"

def test_rewriter_strips_pure_fillers():
    from core.memory import _rewrite_query
    result = _rewrite_query("please tell me about database")
    assert "please" not in result
    assert "database" in result

def test_rewriter_expands_abbreviations():
    from core.memory import _rewrite_query
    assert "python"   in _rewrite_query("fix py error")
    assert "error"    in _rewrite_query("fix err cfg")
    assert "database" in _rewrite_query("chroma db issue")

def test_rewriter_never_returns_empty():
    from core.memory import _rewrite_query
    assert len(_rewrite_query("the a an").strip()) > 0

def test_rewriter_handles_empty_input():
    from core.memory import _rewrite_query
    assert _rewrite_query("") == "general"

# -- Store (acceptance, not recall exact-match) --------------------------------

def test_store_episodic_accepted():
    from core.memory import memory
    r = memory.store_episodic(
        "Fixed syntax error in tools/web.py by adding missing colon after def",
        importance=7, goal="fix bug", outcome="success",
    )
    assert r["status"] in ("stored", "skipped_duplicate"), f"Unexpected: {r}"

def test_store_semantic_accepted():
    from core.memory import memory
    r = memory.store_semantic(
        "ChromaDB collections are isolated vector spaces supporting cosine similarity",
        importance=6, tags="chromadb,vectors",
    )
    assert r["status"] in ("stored", "skipped_duplicate"), f"Unexpected: {r}"

def test_store_procedural_accepted():
    from core.memory import memory
    r = memory.store_procedural(
        "To add a new MCP tool: decorate function with @tool in tools/ directory",
        importance=8, tags="mcp,tools",
    )
    assert r["status"] in ("stored", "skipped_duplicate"), f"Unexpected: {r}"

def test_store_rejects_oversized_text():
    from tools.memory_tool import memory
    big_text = "x" * 51_000
    r = memory(action="store", text=big_text, memory_type="semantic", importance=5)
    assert r["status"] == "error"
    assert "50000 byte limit" in r["error"]

# -- Recall structure (not content-dependent) ----------------------------------

def test_recall_returns_list():
    from core.memory import memory
    results = memory.recall("chromadb vector database", top_k=5, min_score=0.0)
    assert isinstance(results, list)

def test_recall_result_has_required_fields():
    from core.memory import memory
    results = memory.recall("python error fix", top_k=3, min_score=0.0)
    for r in results:
        assert "text"       in r
        assert "score"      in r
        assert "type"       in r
        assert "collection" in r

def test_recall_sorted_by_score():
    from core.memory import memory
    results = memory.recall("memory store chromadb", top_k=10, min_score=0.0)
    scores  = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)

# -- Stats --------------------------------------------------------------------

def test_stats_structure():
    from core.memory import memory
    stats = memory.stats()
    for col in ["episodic", "semantic", "procedural"]:
        assert col in stats
        assert isinstance(stats[col].get("count"), int)
        assert stats[col]["count"] >= 0

# -- Prune protection ---------------------------------------------------------

def test_prune_dry_run_no_delete():
    from core.memory import memory
    before = memory.stats()
    memory.prune(dry_run=True, max_age_days=0, min_importance=10)
    after  = memory.stats()
    for col in ["episodic", "semantic", "procedural"]:
        assert before[col]["count"] == after[col]["count"]

def test_prune_protects_procedural_by_default():
    from core.memory import memory
    before = memory.stats()["procedural"]["count"]
    memory.prune(dry_run=False, max_age_days=0, min_importance=10)
    assert memory.stats()["procedural"]["count"] == before

