"""Test execute_store_chunked (core memory v1.1).

Uses the real ChromaDB store (same pattern as test_write_ops.py).

Test design notes (READ BEFORE EDITING):

  1. UNIQUE TEXT PER RUN: Each test appends a UUID suffix to chunk text.
     The persistent ChromaDB at memory_db/ retains data between runs.
     Static text ("ChunkAlpha_0: ...") would be flagged as a hash duplicate
     on the second run. UUID suffixes guarantee the text is unique every run.

  2. col.get() NOT recall() FOR METADATA: Metadata verification uses col.get()
     (direct ChromaDB access, deterministic). recall() uses vector similarity
     + fetch limits (fetch_k=20), so in a persistent DB with hundreds of
     memories, short synthetic chunks don't reliably appear in top-K.

  3. _direct_store() FOR PRE-EXISTING MEMORY SETUP: Tests that need a
     pre-existing memory MUST use _direct_store(), NOT memory.store_semantic().
     store_semantic() runs two-layer dedup (hash + vector) and can return
     "skipped_duplicate" if the text is semantically similar to ANY existing
     memory — even with a unique UUID marker. This makes store_semantic()
     non-deterministic for test setup. _direct_store() bypasses dedup
     entirely (direct col.add() + manual _hash_cache sync), guaranteeing the
     memory is in the DB. See test_write_ops.py — it accepts
     ("stored", "skipped_duplicate") on setup, but chunked tests need exact
     counts and can't tolerate setup skips.

One concern per test class — no generic names.

Concerns covered:
  - store_chunked stores all chunks
  - chunks share source_doc_id
  - chunk_index and chunk_count metadata correct
  - recall result dicts include chunk metadata fields
  - non-chunked memories have default chunk metadata
  - hash dedup skips exact duplicate chunks (including intra-batch)
  - episodic collection support
"""
from __future__ import annotations

import time
import uuid
import pytest
from core.memory_engine import memory
from core.memory_backend.scoring import normalize_and_hash


def _unique_marker() -> str:
    """Generate a short unique suffix to prevent hash collisions across test runs.

    The persistent ChromaDB retains memories between runs. Without this,
    static test text would be flagged as a hash duplicate on the second run
    (status='skipped_duplicate' instead of 'stored'), breaking count assertions.
    """
    return uuid.uuid4().hex[:8]


def _direct_store(text: str, collection: str = "semantic", importance: int = 5) -> str:
    """Insert a memory directly into ChromaDB, bypassing the dedup pipeline.

    WHY THIS EXISTS:
      memory.store_semantic() runs two-layer dedup (hash + vector). Even with
      a unique UUID marker, vector dedup can flag the text as semantically
      similar to an existing memory and return "skipped_duplicate" — meaning
      the memory was NEVER STORED. This breaks tests that need a pre-existing
      memory for setup (e.g., testing that store_chunked skips duplicates of it).

      _direct_store() bypasses execute_store() entirely:
        1. Calls col.add() directly (no dedup checks)
        2. Manually adds the text_hash to store._hash_cache (so store_chunked's
           hash guard will catch it as a duplicate)

    Returns the text_hash so callers can verify via col.get() if needed.
    """
    text_hash = normalize_and_hash(text)
    col = memory._col(collection)
    mem_id = str(uuid.uuid4())
    now = int(time.time())
    col.add(
        documents=[text],
        ids=[mem_id],
        metadatas=[{
            "type": collection,
            "importance": importance,
            "tags": "",
            "timestamp": now,
            "trace_id": "",
            "goal": "",
            "outcome": "unknown",
            "tools_used": "",
            "source": "",
            "text_hash": text_hash,
            "reinforcement_count": 0,
            "last_reinforced": now,
        }],
    )
    # Sync the hash cache so store_chunked's hash guard catches this as a duplicate
    memory._hash_cache.add(text_hash)
    return text_hash


# ─────────────────────────────────────────────────────────────────────────────
# Basic chunked store — all chunks stored with correct metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestStoreChunkedBasic:
    """store_chunked must store all chunks with linked metadata."""

    def test_all_chunks_stored(self):
        """All non-duplicate chunks are stored in a single batch."""
        marker = _unique_marker()
        chunks = [
            f"ChunkAlpha_{marker}_{i}: This is chunk number {i} of a test document." for i in range(5)
        ]
        result = memory.store_chunked(
            chunks=chunks,
            memory_type="semantic",
            importance=7,
            tags="test,chunked",
            trace_id=f"test_chunked_basic_{marker}",
            source="test_store_chunked",
        )
        assert result["status"] == "stored"
        assert result["stored"] == 5
        assert result["skipped_duplicates"] == 0
        assert result["chunk_count"] == 5
        assert "source_doc_id" in result
        assert len(result["source_doc_id"]) > 0

    def test_chunks_share_source_doc_id(self):
        """All chunks from the same document share the same source_doc_id.
        Verified via col.get() (deterministic) — recall() is fuzzy and
        unreliable for short synthetic chunks in a persistent DB."""
        marker = _unique_marker()
        chunks = [f"ChunkBeta_{marker}_{i}: Shared doc test {i}." for i in range(3)]
        result = memory.store_chunked(
            chunks=chunks,
            memory_type="semantic",
            trace_id=f"test_shared_doc_id_{marker}",
        )
        assert result["status"] == "stored"
        source_doc_id = result["source_doc_id"]

        # Directly query ChromaDB — bypasses recall's vector similarity + fetch limits
        col = memory._col("semantic")
        all_data = col.get(include=["metadatas", "documents"])
        chunk_results = [
            meta for meta in all_data["metadatas"]
            if meta.get("source_doc_id") == source_doc_id
        ]
        assert len(chunk_results) == 3
        for meta in chunk_results:
            assert meta["source_doc_id"] == source_doc_id
            assert meta["chunk_count"] == 3

    def test_chunk_index_and_count_correct(self):
        """chunk_index is 0-based and chunk_count matches total."""
        marker = _unique_marker()
        chunks = [f"ChunkGamma_{marker}_{i}: Index test {i}." for i in range(4)]
        result = memory.store_chunked(
            chunks=chunks,
            memory_type="semantic",
            trace_id=f"test_chunk_index_{marker}",
        )
        assert result["status"] == "stored"
        source_doc_id = result["source_doc_id"]

        # Directly query ChromaDB
        col = memory._col("semantic")
        all_data = col.get(include=["metadatas"])
        chunk_metas = [
            meta for meta in all_data["metadatas"]
            if meta.get("source_doc_id") == source_doc_id
        ]
        assert len(chunk_metas) == 4
        # Verify each chunk has correct index and count
        indices = sorted(meta["chunk_index"] for meta in chunk_metas)
        assert indices == [0, 1, 2, 3]
        for meta in chunk_metas:
            assert meta["chunk_count"] == 4


# ─────────────────────────────────────────────────────────────────────────────
# Recall result shape — field presence (not specific chunk retrieval)
# ─────────────────────────────────────────────────────────────────────────────

class TestRecallChunkMetadata:
    """recall() result dicts must include source_doc_id, chunk_index, chunk_count keys.

    We test FIELD PRESENCE, not specific chunk retrieval — recall uses vector
    similarity + fetch limits and is unreliable for finding specific short chunks
    in a persistent DB. col.get() verifies the metadata is stored correctly
    (see TestStoreChunkedBasic above). Here we just verify the recall result
    dict has the new keys."""

    def test_recall_result_has_chunk_fields(self):
        """Every recall result dict includes source_doc_id, chunk_index, chunk_count keys."""
        marker = _unique_marker()
        # Store something so the collection isn't empty
        memory.store_semantic(
            text=f"ChunkFieldTest_{marker}: verify recall result dict has chunk metadata keys.",
            importance=5, trace_id=f"test_fields_{marker}",
        )

        results = memory.recall(
            query=f"chunk metadata fields test {marker}",
            collections=["semantic"],
            top_k=5,
            min_score=0.0,
        )
        # If we got any results, verify they have the new fields
        assert len(results) >= 1, "recall returned no results — DB may be empty"
        for r in results:
            assert "source_doc_id" in r, "recall result missing source_doc_id key"
            assert "chunk_index" in r, "recall result missing chunk_index key"
            assert "chunk_count" in r, "recall result missing chunk_count key"

    def test_non_chunked_memory_has_default_metadata(self):
        """A non-chunked memory (stored via _direct_store, NOT store_semantic)
        has default chunk metadata (source_doc_id='', chunk_index=None,
        chunk_count=0).

        Uses _direct_store() because store_semantic() can return
        skipped_duplicate (vector dedup) and never actually store the memory,
        making it unfindable via col.get(). See _direct_store() docstring."""
        marker = _unique_marker()
        text = f"NonChunkedEpsilon_{marker}: This is a regular non-chunked memory for metadata test."
        text_hash = _direct_store(text, collection="semantic")

        # Directly query ChromaDB — find our memory by text_hash
        col = memory._col("semantic")
        all_data = col.get(include=["metadatas", "documents"])
        epsilon_metas = [
            meta for meta in all_data["metadatas"]
            if meta.get("text_hash") == text_hash
        ]
        assert len(epsilon_metas) >= 1, "Non-chunked memory not found in DB"
        for meta in epsilon_metas:
            # Non-chunked memories don't have chunk metadata keys — .get() returns defaults
            assert meta.get("source_doc_id", "") == ""
            assert meta.get("chunk_index", None) is None
            assert meta.get("chunk_count", 0) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Hash dedup — duplicate chunks skipped (including intra-batch)
# ─────────────────────────────────────────────────────────────────────────────

class TestStoreChunkedDedup:
    """store_chunked uses hash dedup (exact match only) — duplicate chunks are skipped.

    v1.1 V2 fix: intra-batch duplicates (two identical chunks in the same
    store_chunked call) are now caught via batch_hashes tracking.

    v1.1 V4 fix: pre-existing memory setup uses _direct_store() instead of
    store_semantic(). store_semantic() runs vector dedup and can return
    skipped_duplicate (memory never stored), breaking the test setup.
    _direct_store() bypasses dedup, guaranteeing the memory is in the DB
    and its hash is in _hash_cache."""

    def test_exact_duplicate_chunks_skipped(self):
        """If two chunks have identical text, the second is skipped (hash dedup)."""
        marker = _unique_marker()
        dup_text = f"ChunkZeta_unique_{marker}: First unique chunk."
        chunks = [
            dup_text,
            dup_text,  # exact duplicate (intra-batch)
            f"ChunkZeta_other_{marker}: Different chunk.",
        ]
        result = memory.store_chunked(
            chunks=chunks,
            memory_type="semantic",
            trace_id=f"test_dedup_chunks_{marker}",
        )
        assert result["status"] == "stored"
        # 2 stored (first + third), 1 skipped (intra-batch duplicate of first)
        assert result["stored"] == 2
        assert result["skipped_duplicates"] == 1
        assert result["chunk_count"] == 3  # total input count, not stored count

    def test_pre_existing_exact_match_skipped(self):
        """If a chunk's text exactly matches an existing memory, it's skipped.

        Uses _direct_store() for setup — store_semantic() can return
        skipped_duplicate (vector dedup) and never store the memory."""
        marker = _unique_marker()
        text = f"ChunkEta_preexisting_{marker}: This text already exists in memory."
        # Directly insert (bypasses dedup) + sync hash cache
        _direct_store(text, collection="semantic")

        # Now try to store it as part of a chunked batch
        result = memory.store_chunked(
            chunks=[text, f"ChunkEta_new_{marker}: This is a genuinely new chunk."],
            memory_type="semantic",
            trace_id=f"test_pre_existing_chunked_{marker}",
        )
        assert result["status"] == "stored"
        # 1 stored (the new one), 1 skipped (exact match with existing)
        assert result["stored"] == 1
        assert result["skipped_duplicates"] == 1

    def test_all_duplicates_returns_skipped_status(self):
        """If ALL chunks are duplicates, status is skipped_duplicate (not stored).

        Uses _direct_store() for setup — store_semantic() can return
        skipped_duplicate (vector dedup) and never store the memory."""
        marker = _unique_marker()
        text = f"ChunkIota_dup_{marker}: This will be stored then duplicated."
        # Directly insert (bypasses dedup) + sync hash cache
        _direct_store(text, collection="semantic")

        # Now try to store only duplicates
        result = memory.store_chunked(
            chunks=[text, text, text],
            memory_type="semantic",
            trace_id=f"test_all_dups_{marker}",
        )
        assert result["status"] == "skipped_duplicate"
        assert result["reason"] == "all_chunks_duplicate_or_empty"
        assert result["stored"] == 0
        assert result["skipped_duplicates"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# Episodic collection support
# ─────────────────────────────────────────────────────────────────────────────

class TestStoreChunkedEpisodic:
    """store_chunked works on episodic collection (not just semantic)."""

    def test_episodic_chunked_store(self):
        """Chunks can be stored in the episodic collection."""
        marker = _unique_marker()
        chunks = [
            f"ChunkTheta_epi_{marker}_{i}: Episodic event chunk {i}." for i in range(3)
        ]
        result = memory.store_chunked(
            chunks=chunks,
            memory_type="episodic",
            importance=6,
            tags="test,episodic,chunked",
            trace_id=f"test_episodic_chunked_{marker}",
            goal="test episodic chunking",
            outcome="success",
        )
        assert result["status"] == "stored"
        assert result["stored"] == 3
        assert result["collection"] == "episodic"
        assert "source_doc_id" in result
        source_doc_id = result["source_doc_id"]

        # Verify via col.get() that chunks are in episodic with correct metadata
        col = memory._col("episodic")
        all_data = col.get(include=["metadatas"])
        theta_metas = [
            meta for meta in all_data["metadatas"]
            if meta.get("source_doc_id") == source_doc_id
        ]
        assert len(theta_metas) == 3
        for meta in theta_metas:
            assert meta["type"] == "episodic"
            assert meta["source_doc_id"] == source_doc_id
            assert meta["chunk_count"] == 3
