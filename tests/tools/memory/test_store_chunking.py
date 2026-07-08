"""Test memory store action with chunking (v1.3).

Tests the tool-layer store action when chunk=True:
  - chunk=True calls store_chunked (not store)
  - chunk=True on procedural is rejected
  - chunk=False (default) still calls store (not store_chunked)
  - chunk_method / chunk_size are passed through
  - chonkie errors are caught and returned as fail()

Mock strategy: mock_store fixture (from conftest) mocks _mem().
_chunk_text is patched per-test to avoid the chonkie dependency.

One concern per test class — no generic names.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest
from tools.memory import memory


# ─────────────────────────────────────────────────────────────────────────────
# chunk=True routes to store_chunked (not store)
# ─────────────────────────────────────────────────────────────────────────────

class TestChunkedStoreRouting:
    """v1.3: chunk=True must call store_chunked(), not store()."""

    def test_chunk_true_calls_store_chunked(self, mock_cfg, mock_store):
        """When chunk=True, the backend's store_chunked() is called."""
        mock_store.store_chunked.return_value = {
            "status": "stored",
            "source_doc_id": "test-uuid",
            "stored": 3,
            "skipped_duplicates": 0,
            "chunk_count": 3,
            "collection": "semantic",
        }
        with patch("tools.memory_ops.actions.store._chunk_text", return_value=["c1", "c2", "c3"]):
            result = memory(
                action="store",
                text="Some long text that will be chunked.",
                memory_type="semantic",
                chunk=True,
                chunk_size=128,
            )
        assert result["status"] == "success"
        mock_store.store_chunked.assert_called_once()
        mock_store.store.assert_not_called()

    def test_chunk_false_calls_store_not_chunked(self, mock_cfg, mock_store):
        """When chunk=False (default), the standard store() is called."""
        with patch("tools.memory_ops.actions.store._chunk_text") as mock_chunk:
            result = memory(
                action="store",
                text="Short text.",
                memory_type="semantic",
                chunk=False,
            )
        assert result["status"] == "success"
        mock_store.store.assert_called_once()
        mock_store.store_chunked.assert_not_called()
        mock_chunk.assert_not_called()  # _chunk_text should not be called

    def test_default_is_no_chunk(self, mock_cfg, mock_store):
        """Omitting chunk param entirely defaults to non-chunked store."""
        with patch("tools.memory_ops.actions.store._chunk_text") as mock_chunk:
            result = memory(
                action="store",
                text="Short text.",
                memory_type="semantic",
            )
        assert result["status"] == "success"
        mock_store.store.assert_called_once()
        mock_chunk.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Procedural collection rejection
# ─────────────────────────────────────────────────────────────────────────────

class TestProceduralRejection:
    """v1.3: chunk=True on procedural must fail — reinforcement is nonsensical
    for chunks."""

    def test_procedural_with_chunk_rejected(self, mock_cfg, mock_store):
        """chunk=True + memory_type='procedural' → clear error, never reaches backend."""
        with patch("tools.memory_ops.actions.store._chunk_text") as mock_chunk:
            result = memory(
                action="store",
                text="Some rule text.",
                memory_type="procedural",
                chunk=True,
            )
        assert result["status"] == "error"
        assert "procedural" in result["error"].lower()
        assert "reinforcement" in result["error"].lower() or "chunk" in result["error"].lower()
        # Backend must never be called
        mock_store.store_chunked.assert_not_called()
        mock_store.store.assert_not_called()
        mock_chunk.assert_not_called()

    def test_episodic_with_chunk_allowed(self, mock_cfg, mock_store):
        """chunk=True + memory_type='episodic' → allowed (episodic supports chunking)."""
        mock_store.store_chunked.return_value = {
            "status": "stored", "source_doc_id": "x", "stored": 2,
            "skipped_duplicates": 0, "chunk_count": 2, "collection": "episodic",
        }
        with patch("tools.memory_ops.actions.store._chunk_text", return_value=["c1", "c2"]):
            result = memory(
                action="store",
                text="Long episodic text.",
                memory_type="episodic",
                chunk=True,
            )
        assert result["status"] == "success"
        mock_store.store_chunked.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Chunk method and size pass-through
# ─────────────────────────────────────────────────────────────────────────────

class TestChunkParamsPassThrough:
    """v1.3: chunk_method and chunk_size are passed to _chunk_text."""

    def test_token_method_passed_through(self, mock_cfg, mock_store):
        mock_store.store_chunked.return_value = {
            "status": "stored", "source_doc_id": "x", "stored": 2,
            "skipped_duplicates": 0, "chunk_count": 2, "collection": "semantic",
        }
        with patch("tools.memory_ops.actions.store._chunk_text", return_value=["c1", "c2"]) as mock_chunk:
            result = memory(
                action="store",
                text="Some text.",
                memory_type="semantic",
                chunk=True,
                chunk_method="token",
                chunk_size=256,
            )
        assert result["status"] == "success"
        mock_chunk.assert_called_once_with("Some text.", "token", 256)

    def test_sentence_method_passed_through(self, mock_cfg, mock_store):
        mock_store.store_chunked.return_value = {
            "status": "stored", "source_doc_id": "x", "stored": 2,
            "skipped_duplicates": 0, "chunk_count": 2, "collection": "semantic",
        }
        with patch("tools.memory_ops.actions.store._chunk_text", return_value=["c1", "c2"]) as mock_chunk:
            result = memory(
                action="store",
                text="Some text.",
                memory_type="semantic",
                chunk=True,
                chunk_method="sentence",
                chunk_size=512,
            )
        assert result["status"] == "success"
        mock_chunk.assert_called_once_with("Some text.", "sentence", 512)

    def test_default_chunk_size_is_512(self, mock_cfg, mock_store):
        """If chunk_size is omitted, default 512 is used."""
        mock_store.store_chunked.return_value = {
            "status": "stored", "source_doc_id": "x", "stored": 1,
            "skipped_duplicates": 0, "chunk_count": 1, "collection": "semantic",
        }
        with patch("tools.memory_ops.actions.store._chunk_text", return_value=["c1"]) as mock_chunk:
            result = memory(
                action="store",
                text="Some text.",
                memory_type="semantic",
                chunk=True,
            )
        assert result["status"] == "success"
        # Default chunk_size=512, default chunk_method="token"
        mock_chunk.assert_called_once_with("Some text.", "token", 512)


# ─────────────────────────────────────────────────────────────────────────────
# Error handling
# ─────────────────────────────────────────────────────────────────────────────

class TestChunkingErrors:
    """v1.3: chunking errors (chonkie missing, invalid method) are caught."""

    def test_chonkie_missing_returns_error(self, mock_cfg, mock_store):
        """If _chunk_text raises RuntimeError (chonkie not installed), return fail()."""
        with patch("tools.memory_ops.actions.store._chunk_text", side_effect=RuntimeError("chonkie is not installed")):
            result = memory(
                action="store",
                text="Some text.",
                memory_type="semantic",
                chunk=True,
            )
        assert result["status"] == "error"
        assert "chonkie" in result["error"].lower()
        mock_store.store_chunked.assert_not_called()

    def test_invalid_chunk_method_returns_error(self, mock_cfg, mock_store):
        """If _chunk_text raises ValueError (invalid method), return fail()."""
        with patch("tools.memory_ops.actions.store._chunk_text", side_effect=ValueError("chunk_method must be 'token' or 'sentence'")):
            result = memory(
                action="store",
                text="Some text.",
                memory_type="semantic",
                chunk=True,
                chunk_method="paragraph",
            )
        assert result["status"] == "error"
        assert "chunking failed" in result["error"].lower()
        mock_store.store_chunked.assert_not_called()

    def test_empty_chunks_returns_error(self, mock_cfg, mock_store):
        """If _chunk_text returns [], return fail() — nothing to store."""
        with patch("tools.memory_ops.actions.store._chunk_text", return_value=[]):
            result = memory(
                action="store",
                text="Some text.",
                memory_type="semantic",
                chunk=True,
            )
        assert result["status"] == "error"
        assert "0 chunks" in result["error"].lower()
        mock_store.store_chunked.assert_not_called()
